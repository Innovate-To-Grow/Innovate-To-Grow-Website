"""Client IPs and the budget counters' reserve / settle semantics."""

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings

from apps.system_intelligence.services.public_assistant import budget

from .budget_helpers import AI_SEARCH, AI_SEARCH_GLOBAL_KEY, ASSISTANT, ASSISTANT_GLOBAL_KEY, BUDGET_LOGGER


class ClientIpTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_remote_addr_fallback(self):
        request = self.factory.get("/", REMOTE_ADDR="203.0.113.7")
        self.assertEqual(budget.client_ip(request), "203.0.113.7")

    def test_forwarded_leftmost_without_num_proxies(self):
        request = self.factory.get("/", HTTP_X_FORWARDED_FOR="1.1.1.1, 2.2.2.2, 3.3.3.3", REMOTE_ADDR="10.0.0.1")
        self.assertEqual(budget.client_ip(request), "1.1.1.1")

    @override_settings(NUM_PROXIES=2)
    def test_forwarded_with_num_proxies(self):
        request = self.factory.get("/", HTTP_X_FORWARDED_FOR="1.1.1.1, 2.2.2.2, 3.3.3.3", REMOTE_ADDR="10.0.0.1")
        # 3 entries, 2 trusted hops -> Nth-from-right is index 1.
        self.assertEqual(budget.client_ip(request), "2.2.2.2")

    @override_settings(NUM_PROXIES=5)
    def test_forwarded_with_num_proxies_clamped(self):
        request = self.factory.get("/", HTTP_X_FORWARDED_FOR="1.1.1.1, 2.2.2.2")
        self.assertEqual(budget.client_ip(request), "1.1.1.1")

    def test_empty_forwarded_falls_back(self):
        request = self.factory.get("/", HTTP_X_FORWARDED_FOR="  ,  ", REMOTE_ADDR="9.9.9.9")
        self.assertEqual(budget.client_ip(request), "9.9.9.9")


@override_settings(PUBLIC_ASSISTANT_ALLOW_LOCAL_BUDGET=True)
class BudgetCounterTests(TestCase):
    def setUp(self):
        cache.clear()
        self.ip_hash = budget.hash_ip("198.51.100.4")

    def test_hash_ip_is_deterministic_and_hex(self):
        again = budget.hash_ip("198.51.100.4")
        self.assertEqual(self.ip_hash, again)
        self.assertEqual(len(self.ip_hash), 64)

    def test_budget_key_uses_hash(self):
        self.assertEqual(budget.budget_key(self.ip_hash), f"assistant:tokens:{self.ip_hash}")

    def test_tokens_used_defaults_to_zero(self):
        self.assertEqual(budget.tokens_used(self.ip_hash), 0)

    def test_record_usage_increments(self):
        budget.record_usage(self.ip_hash, 100, 86400)
        budget.record_usage(self.ip_hash, 50, 86400)
        self.assertEqual(budget.tokens_used(self.ip_hash), 150)

    def test_record_usage_ignores_non_positive(self):
        budget.record_usage(self.ip_hash, 0, 86400)
        budget.record_usage(self.ip_hash, -5, 86400)
        self.assertEqual(budget.tokens_used(self.ip_hash), 0)

    def test_check_budget_unlimited_when_limit_non_positive(self):
        budget.record_usage(self.ip_hash, 10_000, 86400)
        self.assertTrue(budget.check_budget(self.ip_hash, 0))
        self.assertTrue(budget.check_budget(self.ip_hash, -1))

    def test_check_budget_boundary(self):
        budget.record_usage(self.ip_hash, 100, 86400)
        self.assertFalse(budget.check_budget(self.ip_hash, 100))
        self.assertTrue(budget.check_budget(self.ip_hash, 101))

    def test_record_usage_recovers_from_incr_value_error(self):
        # Simulate the key expiring between add() and incr() (incr raises ValueError).
        with patch.object(cache, "incr", side_effect=ValueError):
            budget.record_usage(self.ip_hash, 25, 86400)
        # The fallback set() path stores the value.
        self.assertEqual(budget.tokens_used(self.ip_hash), 25)

    def test_record_usage_clamps_zero_window(self):
        # window_seconds=0 means "expire immediately" in Django's cache, which
        # would silently disable the budget; record_usage must clamp it so the
        # counter actually persists and the limit is enforced.
        budget.record_usage(self.ip_hash, 200, 0)
        self.assertEqual(budget.tokens_used(self.ip_hash), 200)
        self.assertFalse(budget.check_budget(self.ip_hash, 100))

    def test_record_usage_retries_incr_once(self):
        calls = {"n": 0}
        real_incr = cache.incr

        def flaky_incr(key, delta=1):
            calls["n"] += 1
            if calls["n"] == 1:
                raise ValueError("expired")
            return real_incr(key, delta)

        with patch.object(cache, "incr", side_effect=flaky_incr):
            budget.record_usage(self.ip_hash, 30, 86400)
        self.assertEqual(budget.tokens_used(self.ip_hash), 30)

    def test_reservation_reconciles_estimate_to_actual_usage(self):
        reservation = budget.reserve_budget(
            self.ip_hash,
            estimated_input_tokens=100,
            maximum_output_tokens=50,
            limit=1000,
            window_seconds=86400,
        )
        self.assertIsNotNone(reservation)
        self.assertEqual(budget.tokens_used(self.ip_hash), 150)

        budget.reconcile_budget(reservation, 80)

        self.assertEqual(budget.tokens_used(self.ip_hash), 80)

    def test_reservation_does_not_carry_an_expired_counter_into_a_new_window(self):
        cache.set(budget.budget_key(self.ip_hash), 90, timeout=86400)

        with patch.object(cache, "incr", side_effect=ValueError("expired")):
            reservation = budget.reserve_budget(
                self.ip_hash,
                estimated_input_tokens=25,
                maximum_output_tokens=0,
                limit=1000,
                window_seconds=86400,
            )

        self.assertIsNotNone(reservation)
        self.assertEqual(budget.tokens_used(self.ip_hash), 25)

    def test_failed_invocation_releases_reservation(self):
        reservation = budget.reserve_budget(
            self.ip_hash,
            estimated_input_tokens=100,
            maximum_output_tokens=50,
            limit=1000,
            window_seconds=86400,
        )
        budget.release_budget(reservation)
        self.assertEqual(budget.tokens_used(self.ip_hash), 0)

    def test_late_reconcile_does_not_mutate_the_next_budget_window(self):
        reservation = budget.reserve_budget(
            self.ip_hash,
            estimated_input_tokens=100,
            maximum_output_tokens=50,
            limit=1000,
            window_seconds=86400,
        )
        self.assertIsNotNone(reservation)

        # Simulate the original fixed window expiring while the model call is
        # still in flight, followed by usage in a fresh window.
        cache.delete(reservation.budget_cache_key)
        cache.delete(reservation.window_cache_key)
        budget.record_usage(self.ip_hash, 40, 86400)

        budget.reconcile_budget(reservation, 80)

        self.assertEqual(budget.tokens_used(self.ip_hash), 40)
        self.assertIsNone(cache.get(reservation.reservation_cache_key))

    def test_late_release_does_not_mutate_the_next_budget_window(self):
        reservation = budget.reserve_budget(
            self.ip_hash,
            estimated_input_tokens=100,
            maximum_output_tokens=50,
            limit=1000,
            window_seconds=86400,
        )
        self.assertIsNotNone(reservation)

        cache.delete(reservation.budget_cache_key)
        cache.delete(reservation.window_cache_key)
        budget.record_usage(self.ip_hash, 40, 86400)

        budget.release_budget(reservation)

        self.assertEqual(budget.tokens_used(self.ip_hash), 40)
        self.assertIsNone(cache.get(reservation.reservation_cache_key))

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

    def _reserve_150(self):
        return budget.reserve_budget(
            self.ip_hash,
            estimated_input_tokens=100,
            maximum_output_tokens=50,
            limit=1000,
            window_seconds=86400,
        )

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

    def _reserve_for(self, feature, *, amount=150):
        return budget.reserve_budget(
            self.ip_hash,
            estimated_input_tokens=amount,
            maximum_output_tokens=0,
            limit=0,
            window_seconds=86400,
            global_limit=5000,
            feature=feature,
        )

    def test_each_feature_charges_its_own_global_counter(self):
        chat = self._reserve_for(ASSISTANT, amount=150)
        search = self._reserve_for(AI_SEARCH, amount=70)

        self.assertEqual(chat.global_reservation.actor_key, ASSISTANT_GLOBAL_KEY)
        self.assertEqual(search.global_reservation.actor_key, AI_SEARCH_GLOBAL_KEY)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 150)
        self.assertEqual(budget.global_tokens_used(AI_SEARCH), 70)
        self.assertEqual(budget.tokens_used(self.ip_hash), 220)

        budget.release_budget(chat)
        budget.reconcile_budget(search, 30)

        self.assertEqual(budget.global_tokens_used(ASSISTANT), 0)
        self.assertEqual(budget.global_tokens_used(AI_SEARCH), 30)
        self.assertEqual(budget.tokens_used(self.ip_hash), 30)

    def test_an_exhausted_feature_does_not_refuse_the_other_one(self):
        budget.record_usage(ASSISTANT_GLOBAL_KEY, 5000, 86400)

        with self.assertLogs(BUDGET_LOGGER, level="WARNING") as logs:
            refused = self._reserve_for(ASSISTANT)
        admitted = self._reserve_for(AI_SEARCH)

        self.assertIsNone(refused)
        self.assertIsNotNone(admitted)
        self.assertEqual(len(logs.output), 1)
        self.assertIn("global token budget exhausted for Public assistant", logs.output[0])
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 5000)
        self.assertEqual(budget.global_tokens_used(AI_SEARCH), 150)

    def test_a_global_limit_needs_a_known_feature(self):
        for feature in (None, "", "chat", ["assistant"]):
            for global_limit in (5000, 0):
                with self.subTest(feature=feature, global_limit=global_limit), self.assertRaises(ValueError):
                    budget.reserve_budget(
                        self.ip_hash,
                        estimated_input_tokens=10,
                        maximum_output_tokens=0,
                        limit=0,
                        window_seconds=86400,
                        global_limit=global_limit,
                        feature=feature,
                    )
        self.assertEqual(budget.tokens_used(self.ip_hash), 0)
        for feature in (ASSISTANT, AI_SEARCH):
            self.assertEqual(budget.global_tokens_used(feature), 0)

    def test_unparsable_provider_usage_settles_the_cache_reservation_at_the_reserved_amount(self):
        reservation = self._reserve_for(ASSISTANT, amount=150)

        with self.assertLogs(BUDGET_LOGGER, level="WARNING") as logs:
            budget.reconcile_budget(reservation, "not-a-number")

        self.assertIn("Unparsable provider token usage", logs.output[0])
        self.assertEqual(budget.tokens_used(self.ip_hash), 150)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 150)
        # The reservation was consumed: settling it again changes nothing.
        self.assertIsNone(cache.get(reservation.reservation_cache_key))
        budget.release_budget(reservation)
        self.assertEqual(budget.tokens_used(self.ip_hash), 150)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 150)

    def test_global_usage_read_out_on_the_cache_path(self):
        self._reserve_for(AI_SEARCH, amount=70)

        usage = budget.global_budget_usage()

        self.assertEqual(
            [(entry.feature, entry.label, entry.tokens_used, entry.window_expires_at) for entry in usage],
            [(ASSISTANT, "Public assistant", 0, None), (AI_SEARCH, "AI search", 70, None)],
        )
