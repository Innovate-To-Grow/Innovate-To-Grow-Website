from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from django.core.cache import cache
from django.test import override_settings

from apps.system_intelligence.services.public_assistant import budget
from apps.system_intelligence.tests.public_assistant.budget.test_budget_counter import _BudgetCounterCase

from .budget_helpers import ASSISTANT, ASSISTANT_GLOBAL_KEY


@override_settings(PUBLIC_ASSISTANT_ALLOW_LOCAL_BUDGET=True)
class BudgetCounterTests(_BudgetCounterCase):
    def test_simultaneous_reservations_cannot_overspend_limit(self):
        def reserve():
            return budget.reserve_budget(
                self.ip_hash,
                estimated_input_tokens=60,
                maximum_output_tokens=0,
                limit=100,
                window_seconds=86400,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            reservations = list(executor.map(lambda _index: reserve(), range(2)))

        self.assertEqual(sum(item is not None for item in reservations), 1)
        self.assertEqual(budget.tokens_used(self.ip_hash), 60)

    def test_cache_settlement_is_idempotent(self):
        reservation = self._reserve_150()

        budget.reconcile_budget(reservation, 80)
        budget.reconcile_budget(reservation, 0)
        budget.release_budget(reservation)

        self.assertEqual(budget.tokens_used(self.ip_hash), 80)

    def test_cache_settlement_never_drives_the_counter_negative(self):
        reservation = self._reserve_150()
        # Something else lowered the counter while the model call was in flight.
        cache.set(reservation.budget_cache_key, 10, timeout=86400)

        budget.release_budget(reservation)

        self.assertEqual(budget.tokens_used(self.ip_hash), 0)

    def test_cache_settlement_tolerates_the_counter_expiring_mid_settlement(self):
        for failing_calls in (1, 2):
            with self.subTest(failing_calls=failing_calls):
                cache.clear()
                reservation = self._reserve_150()
                real_incr = cache.incr
                calls = {"n": 0}

                def incr(key, delta=1, calls=calls, real_incr=real_incr, failing_calls=failing_calls):
                    calls["n"] += 1
                    if failing_calls == 1 or calls["n"] == 2:
                        raise ValueError("expired")
                    # First call of the two-call case: overshoot below zero.
                    return real_incr(key, delta - 1000)

                with patch.object(cache, "incr", side_effect=incr):
                    budget.release_budget(reservation)

                self.assertIsNone(cache.get(reservation.reservation_cache_key))

    def test_record_usage_reseeds_the_window_when_the_counter_expired_before_the_increment(self):
        real_add, real_incr = cache.add, cache.incr
        state = {"incr_calls": 0}

        def incr(key, delta=1):
            state["incr_calls"] += 1
            if state["incr_calls"] == 1:
                # The counter created by add() expired before it could be incremented.
                cache.delete(key)
                raise ValueError("expired")
            return real_incr(key, delta)

        with patch.object(cache, "incr", side_effect=incr), patch.object(cache, "add", wraps=real_add) as add:
            budget.record_usage(self.ip_hash, 30, 86400)

        self.assertEqual(add.call_count, 2)
        self.assertEqual(budget.tokens_used(self.ip_hash), 30)
        self.assertIsNotNone(cache.get(budget._budget_window_key(self.ip_hash)))

    def test_two_level_reservation_charges_and_settles_actor_and_global(self):
        reservation = budget.reserve_budget(
            self.ip_hash,
            estimated_input_tokens=100,
            maximum_output_tokens=50,
            limit=1000,
            window_seconds=86400,
            global_limit=5000,
            feature=ASSISTANT,
        )

        self.assertIsNotNone(reservation.global_reservation)
        self.assertEqual(budget.tokens_used(self.ip_hash), 150)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 150)

        budget.reconcile_budget(reservation, 80)

        self.assertEqual(budget.tokens_used(self.ip_hash), 80)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 80)

    def test_two_level_release_returns_both_charges(self):
        reservation = budget.reserve_budget(
            self.ip_hash,
            estimated_input_tokens=100,
            maximum_output_tokens=50,
            limit=1000,
            window_seconds=86400,
            global_limit=5000,
            feature=ASSISTANT,
        )

        budget.release_budget(reservation)

        self.assertEqual(budget.tokens_used(self.ip_hash), 0)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 0)

    def test_actor_refusal_gives_the_global_charge_back(self):
        budget.record_usage(self.ip_hash, 90, 86400)

        reservation = budget.reserve_budget(
            self.ip_hash,
            estimated_input_tokens=20,
            maximum_output_tokens=0,
            limit=100,
            window_seconds=86400,
            global_limit=5000,
            feature=ASSISTANT,
        )

        self.assertIsNone(reservation)
        self.assertEqual(budget.tokens_used(self.ip_hash), 90)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 0)

    def test_global_refusal_leaves_the_actor_untouched(self):
        budget.record_usage(ASSISTANT_GLOBAL_KEY, 4990, 86400)

        with self.assertLogs("apps.system_intelligence.services.public_assistant.budget", level="WARNING") as logs:
            reservation = budget.reserve_budget(
                self.ip_hash,
                estimated_input_tokens=20,
                maximum_output_tokens=0,
                limit=1000,
                window_seconds=86400,
                global_limit=5000,
                feature=ASSISTANT,
            )

        self.assertIsNone(reservation)
        self.assertEqual(budget.tokens_used(self.ip_hash), 0)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 4990)
        self.assertIn("global token budget exhausted", logs.output[0])

    def test_zero_global_limit_refuses_without_touching_any_counter(self):
        reservation = budget.reserve_budget(
            self.ip_hash,
            estimated_input_tokens=1,
            maximum_output_tokens=0,
            limit=0,
            window_seconds=86400,
            global_limit=0,
            feature=ASSISTANT,
        )

        self.assertIsNone(reservation)
        self.assertEqual(budget.tokens_used(self.ip_hash), 0)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 0)
