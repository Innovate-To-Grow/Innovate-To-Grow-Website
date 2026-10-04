"""Unit tests for the token budget helpers (per-actor and per-feature global)."""

import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Event
from unittest.mock import Mock, patch

from django.core.cache import cache
from django.db import close_old_connections, connection, transaction
from django.db.models import QuerySet
from django.test import RequestFactory, TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.system_intelligence.models import PublicAssistantTokenBudget, PublicAssistantTokenReservation
from apps.system_intelligence.services.public_assistant import budget

ASSISTANT = budget.FEATURE_ASSISTANT
AI_SEARCH = budget.FEATURE_AI_SEARCH
ASSISTANT_GLOBAL_KEY = budget.GLOBAL_BUDGET_KEYS[ASSISTANT]
AI_SEARCH_GLOBAL_KEY = budget.GLOBAL_BUDGET_KEYS[AI_SEARCH]
BUDGET_LOGGER = "apps.system_intelligence.services.public_assistant.budget"


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


@override_settings(PUBLIC_ASSISTANT_ALLOW_LOCAL_BUDGET=False, REDIS_URL="")
class DatabaseBudgetFallbackTests(TestCase):
    def setUp(self):
        self.ip_hash = budget.hash_ip("203.0.113.20")

    @patch.object(budget, "_shared_redis_client")
    def test_reservation_reconcile_and_release_use_the_shared_database(self, redis_connection):
        reservation = budget.reserve_budget(
            self.ip_hash,
            estimated_input_tokens=100,
            maximum_output_tokens=50,
            limit=1000,
            window_seconds=3600,
        )

        self.assertIsNotNone(reservation)
        self.assertTrue(reservation.database)
        self.assertIsNotNone(reservation.database_reservation_id)
        redis_connection.assert_not_called()
        self.assertEqual(budget.tokens_used(self.ip_hash), 150)

        budget.reconcile_budget(reservation, 80)
        self.assertEqual(budget.tokens_used(self.ip_hash), 80)

        second = budget.reserve_budget(
            self.ip_hash,
            estimated_input_tokens=40,
            maximum_output_tokens=10,
            limit=1000,
            window_seconds=3600,
        )
        self.assertEqual(budget.tokens_used(self.ip_hash), 130)
        budget.release_budget(second)
        self.assertEqual(budget.tokens_used(self.ip_hash), 80)
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    def test_database_settlement_is_idempotent(self):
        first = budget.reserve_budget(
            self.ip_hash,
            estimated_input_tokens=60,
            maximum_output_tokens=0,
            limit=1000,
            window_seconds=3600,
        )
        second = budget.reserve_budget(
            self.ip_hash,
            estimated_input_tokens=30,
            maximum_output_tokens=0,
            limit=1000,
            window_seconds=3600,
        )

        budget.reconcile_budget(first, 20)
        self.assertEqual(budget.tokens_used(self.ip_hash), 50)

        budget.reconcile_budget(first, 0)
        budget.release_budget(first)
        self.assertEqual(budget.tokens_used(self.ip_hash), 50)
        self.assertEqual(PublicAssistantTokenReservation.objects.count(), 1)

        budget.release_budget(second)
        self.assertEqual(budget.tokens_used(self.ip_hash), 20)
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    def test_impossible_first_reservation_does_not_anchor_a_window(self):
        reservation = budget.reserve_budget(
            self.ip_hash,
            estimated_input_tokens=101,
            maximum_output_tokens=0,
            limit=100,
            window_seconds=3600,
        )

        self.assertIsNone(reservation)
        self.assertFalse(PublicAssistantTokenBudget.objects.filter(pk=self.ip_hash).exists())
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    def test_database_reservation_enforces_the_limit_atomically(self):
        budget.record_usage(self.ip_hash, 80, 3600)

        reservation = budget.reserve_budget(
            self.ip_hash,
            estimated_input_tokens=21,
            maximum_output_tokens=0,
            limit=100,
            window_seconds=3600,
        )

        self.assertIsNone(reservation)
        self.assertEqual(budget.tokens_used(self.ip_hash), 80)

    def test_late_reconcile_does_not_mutate_a_new_database_window(self):
        reservation = budget.reserve_budget(
            self.ip_hash,
            estimated_input_tokens=100,
            maximum_output_tokens=50,
            limit=1000,
            window_seconds=3600,
        )
        state = PublicAssistantTokenBudget.objects.get(pk=self.ip_hash)
        state.window_id = budget._new_window_id()
        state.tokens_used = 40
        state.window_expires_at = timezone.now() + timedelta(hours=1)
        state.save()

        budget.reconcile_budget(reservation, 80)

        self.assertEqual(budget.tokens_used(self.ip_hash), 40)
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    def test_expired_database_counter_starts_a_fresh_window(self):
        PublicAssistantTokenBudget.objects.create(
            ip_hash=self.ip_hash,
            window_id=budget._new_window_id(),
            tokens_used=999,
            window_expires_at=timezone.now() - timedelta(seconds=1),
        )

        reservation = budget.reserve_budget(
            self.ip_hash,
            estimated_input_tokens=25,
            maximum_output_tokens=0,
            limit=100,
            window_seconds=3600,
        )

        self.assertIsNotNone(reservation)
        self.assertEqual(budget.tokens_used(self.ip_hash), 25)

    def test_cleanup_deletes_only_expired_budget_rows(self):
        expired_hash = budget.hash_ip("203.0.113.21")
        expired = PublicAssistantTokenBudget.objects.create(
            ip_hash=expired_hash,
            window_id=budget._new_window_id(),
            tokens_used=25,
            window_expires_at=timezone.now() - timedelta(seconds=1),
        )
        PublicAssistantTokenReservation.objects.create(
            budget=expired,
            window_id=expired.window_id,
            reserved_tokens=25,
        )
        budget.record_usage(self.ip_hash, 10, 3600)

        self.assertEqual(budget.purge_expired_public_assistant_budgets(), 1)

        self.assertFalse(PublicAssistantTokenBudget.objects.filter(pk=expired_hash).exists())
        self.assertTrue(PublicAssistantTokenBudget.objects.filter(pk=self.ip_hash).exists())
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())


def _budget_row_lock_order(queries, keys):
    """Order in which budget rows were first SELECTed (locked, on PostgreSQL)."""
    order = []
    for query in queries:
        sql = query["sql"]
        if not sql.lstrip().upper().startswith("SELECT") or "publicassistanttokenbudget" not in sql.lower():
            continue
        for key in keys:
            if key in sql and key not in order:
                if connection.features.has_select_for_update:
                    assert "FOR UPDATE" in sql.upper(), sql
                order.append(key)
    return order


@override_settings(PUBLIC_ASSISTANT_ALLOW_LOCAL_BUDGET=False, REDIS_URL="")
class DatabaseTwoLevelBudgetTests(TestCase):
    """Actor budget + global budget on the authoritative database path."""

    def setUp(self):
        cache.clear()
        self.actor = budget.hash_ip("actor-a")
        self.other = budget.hash_ip("actor-b")

    def _reserve(
        self,
        actor=None,
        *,
        amount=150,
        limit=0,
        global_limit=5000,
        window_seconds=3600,
        feature=ASSISTANT,
    ):
        return budget.reserve_budget(
            actor or self.actor,
            estimated_input_tokens=amount,
            maximum_output_tokens=0,
            limit=limit,
            window_seconds=window_seconds,
            global_limit=global_limit,
            feature=feature,
        )

    def test_reservation_charges_the_actor_row_and_the_global_row(self):
        reservation = self._reserve()

        self.assertTrue(reservation.database)
        self.assertEqual(reservation.actor_key, self.actor)
        self.assertEqual(reservation.global_reservation.actor_key, ASSISTANT_GLOBAL_KEY)
        self.assertEqual(budget.tokens_used(self.actor), 150)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 150)
        self.assertEqual(PublicAssistantTokenReservation.objects.count(), 2)
        self.assertEqual(
            set(PublicAssistantTokenBudget.objects.values_list("pk", flat=True)),
            {self.actor, ASSISTANT_GLOBAL_KEY},
        )

    def test_global_budget_is_the_sum_over_all_actors(self):
        self._reserve(self.actor, amount=150)
        self._reserve(self.other, amount=70)

        self.assertEqual(budget.tokens_used(self.actor), 150)
        self.assertEqual(budget.tokens_used(self.other), 70)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 220)

    def test_reconcile_settles_both_levels_to_actual_usage(self):
        reservation = self._reserve()

        budget.reconcile_budget(reservation, 80)

        self.assertEqual(budget.tokens_used(self.actor), 80)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 80)
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    def test_release_returns_both_levels_in_full(self):
        self._reserve(self.other, amount=40)
        reservation = self._reserve()

        budget.release_budget(reservation)

        self.assertEqual(budget.tokens_used(self.actor), 0)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 40)
        self.assertEqual(PublicAssistantTokenReservation.objects.count(), 2)

    def test_two_level_settlement_is_idempotent(self):
        reservation = self._reserve()

        budget.reconcile_budget(reservation, 80)
        budget.reconcile_budget(reservation, 0)
        budget.release_budget(reservation)

        self.assertEqual(budget.tokens_used(self.actor), 80)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 80)

    def test_actor_over_its_limit_is_refused_and_the_global_row_is_not_charged(self):
        self._reserve(self.other, amount=40)
        budget.record_usage(self.actor, 900, 3600)

        self.assertIsNone(self._reserve(amount=150, limit=1000))

        self.assertEqual(budget.tokens_used(self.actor), 900)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 40)
        self.assertEqual(PublicAssistantTokenReservation.objects.count(), 2)

    def test_exhausted_global_budget_refuses_every_actor_and_charges_nobody(self):
        self._reserve(self.other, amount=4900)

        with self.assertLogs("apps.system_intelligence.services.public_assistant.budget", level="WARNING") as logs:
            refused = self._reserve(amount=150)

        self.assertIsNone(refused)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 4900)
        self.assertEqual(budget.tokens_used(self.actor), 0)
        self.assertFalse(PublicAssistantTokenBudget.objects.filter(pk=self.actor).exists())
        self.assertIn("global token budget exhausted", logs.output[0])

    def test_global_refusal_is_logged_at_most_once_a_minute(self):
        self._reserve(self.other, amount=4900)
        with self.assertLogs("apps.system_intelligence.services.public_assistant.budget", level="WARNING") as logs:
            for _ in range(5):
                self.assertIsNone(self._reserve(amount=150))

        self.assertEqual(len(logs.output), 1)

    def test_global_budget_admits_exactly_up_to_its_limit(self):
        self.assertIsNotNone(self._reserve(self.actor, amount=3000, limit=0))
        self.assertIsNotNone(self._reserve(self.other, amount=2000, limit=0))
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 5000)

        with self.assertLogs("apps.system_intelligence.services.public_assistant.budget", level="WARNING"):
            self.assertIsNone(self._reserve(budget.hash_ip("actor-c"), amount=1, limit=0))
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 5000)

    def test_request_larger_than_the_global_limit_creates_no_rows(self):
        with self.assertLogs("apps.system_intelligence.services.public_assistant.budget", level="WARNING"):
            self.assertIsNone(self._reserve(amount=5001, limit=0))

        self.assertFalse(PublicAssistantTokenBudget.objects.exists())

    def test_zero_global_limit_refuses_everything_and_creates_no_rows(self):
        # "Switched off" is a setting, not an incident: no exhaustion alarm.
        with self.assertNoLogs("apps.system_intelligence.services.public_assistant.budget", level="WARNING"):
            self.assertIsNone(self._reserve(amount=1, limit=0, global_limit=0))

        self.assertFalse(PublicAssistantTokenBudget.objects.exists())
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    def test_without_a_global_limit_only_the_actor_row_is_charged(self):
        reservation = self._reserve(global_limit=None)

        self.assertIsNone(reservation.global_reservation)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 0)
        self.assertEqual(budget.tokens_used(self.actor), 150)

    def test_raising_the_global_limit_takes_effect_immediately(self):
        self._reserve(self.other, amount=4900)
        with self.assertLogs("apps.system_intelligence.services.public_assistant.budget", level="WARNING"):
            self.assertIsNone(self._reserve(amount=150, global_limit=5000))

        self.assertIsNotNone(self._reserve(amount=150, global_limit=6000))
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 5050)

    def test_expired_global_window_starts_fresh_while_actor_windows_continue(self):
        self._reserve(self.actor, amount=150, window_seconds=7 * 86400)
        PublicAssistantTokenBudget.objects.filter(pk=ASSISTANT_GLOBAL_KEY).update(
            tokens_used=4999,
            window_expires_at=timezone.now() - timedelta(seconds=1),
        )

        self.assertIsNotNone(self._reserve(self.actor, amount=100, window_seconds=7 * 86400))

        self.assertEqual(budget.global_tokens_used(ASSISTANT), 100)
        self.assertEqual(budget.tokens_used(self.actor), 250)

    def test_global_window_is_twenty_four_hours(self):
        before = timezone.now()
        self._reserve()

        expires_at = PublicAssistantTokenBudget.objects.get(pk=ASSISTANT_GLOBAL_KEY).window_expires_at
        self.assertEqual(budget.GLOBAL_WINDOW_SECONDS, 86400)
        self.assertGreaterEqual(expires_at, before + timedelta(hours=24))
        self.assertLessEqual(expires_at, timezone.now() + timedelta(hours=24))

    def test_late_settlement_only_touches_the_window_it_was_charged_to(self):
        reservation = self._reserve()
        # The global window rolled over while the model call was in flight.
        PublicAssistantTokenBudget.objects.filter(pk=ASSISTANT_GLOBAL_KEY).update(
            window_id=budget._new_window_id(),
            tokens_used=40,
        )

        budget.reconcile_budget(reservation, 80)

        self.assertEqual(budget.global_tokens_used(ASSISTANT), 40)
        self.assertEqual(budget.tokens_used(self.actor), 80)
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    def test_global_charge_is_still_settled_when_the_actor_row_was_purged(self):
        reservation = self._reserve()
        PublicAssistantTokenBudget.objects.filter(pk=self.actor).delete()

        budget.reconcile_budget(reservation, 80)

        self.assertEqual(budget.global_tokens_used(ASSISTANT), 80)
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    def test_actor_charge_is_still_settled_when_the_global_row_was_purged(self):
        reservation = self._reserve()
        PublicAssistantTokenBudget.objects.filter(pk=ASSISTANT_GLOBAL_KEY).delete()

        budget.release_budget(reservation)

        self.assertEqual(budget.tokens_used(self.actor), 0)
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    def test_reserve_locks_only_its_own_global_row_and_before_the_actor_row(self):
        # Every budget row a reservation could touch. A feature must lock its
        # OWN global row, then the actor row, and never the other feature's.
        keys = [self.actor, ASSISTANT_GLOBAL_KEY, AI_SEARCH_GLOBAL_KEY]
        for feature, global_key in ((ASSISTANT, ASSISTANT_GLOBAL_KEY), (AI_SEARCH, AI_SEARCH_GLOBAL_KEY)):
            for label in ("first use", "existing rows"):
                with self.subTest(feature=feature, state=label):
                    with CaptureQueriesContext(connection) as captured:
                        self._reserve(feature=feature)

                    self.assertEqual(
                        _budget_row_lock_order(captured.captured_queries, keys),
                        [global_key, self.actor],
                    )

    def test_settlement_locks_only_its_own_global_row_and_before_the_actor_row(self):
        keys = [self.actor, ASSISTANT_GLOBAL_KEY, AI_SEARCH_GLOBAL_KEY]
        for feature, global_key in ((ASSISTANT, ASSISTANT_GLOBAL_KEY), (AI_SEARCH, AI_SEARCH_GLOBAL_KEY)):
            # Both features' rows exist, so a settlement that touched the wrong one would show.
            self._reserve(self.other, feature=ASSISTANT)
            self._reserve(self.other, feature=AI_SEARCH)
            for label, settle in (
                ("reconcile", lambda reservation: budget.reconcile_budget(reservation, 80)),
                ("release", budget.release_budget),
            ):
                with self.subTest(feature=feature, settlement=label):
                    reservation = self._reserve(feature=feature)
                    with CaptureQueriesContext(connection) as captured:
                        settle(reservation)

                    self.assertEqual(
                        _budget_row_lock_order(captured.captured_queries, keys),
                        [global_key, self.actor],
                    )

    def test_refusal_stays_a_refusal_when_the_alarm_cache_is_down(self):
        self._reserve(self.other, amount=4900)

        with (
            patch.object(budget.cache, "add", side_effect=RuntimeError("cache down")),
            self.assertLogs("apps.system_intelligence.services.public_assistant.budget", level="WARNING") as logs,
        ):
            refused = self._reserve(amount=150)

        self.assertIsNone(refused)
        self.assertIn("global token budget exhausted", logs.output[0])

    def test_partly_settled_reservation_settles_the_remaining_level(self):
        reservation = self._reserve()
        PublicAssistantTokenReservation.objects.filter(
            pk=reservation.global_reservation.database_reservation_id
        ).delete()

        budget.reconcile_budget(reservation, 80)

        # The actor's charge is settled; the global counter is left alone
        # because its reservation record is gone (never settled twice).
        self.assertEqual(budget.tokens_used(self.actor), 80)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 150)
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    def test_settling_a_reservation_without_database_rows_is_a_no_op(self):
        empty = budget.BudgetReservation(
            budget_cache_key="",
            window_cache_key="",
            reservation_cache_key="",
            reserved_tokens=10,
            window_seconds=3600,
            shared_redis=False,
            database=True,
            actor_key=self.actor,
        )

        budget.reconcile_budget(empty, 5)
        budget.release_budget(empty)

        self.assertFalse(PublicAssistantTokenBudget.objects.exists())

    def test_settlement_failure_is_reported_as_backend_unavailable(self):
        reservation = self._reserve()

        with patch.object(budget, "_settle_database_reservation", side_effect=RuntimeError("db down")):
            with self.assertRaises(budget.BudgetBackendUnavailable):
                budget.reconcile_budget(reservation, 80)
            with self.assertRaises(budget.BudgetBackendUnavailable):
                budget.release_budget(reservation)

        # Still settleable once the database is back.
        budget.release_budget(reservation)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 0)

    def test_purge_with_nothing_expired_deletes_nothing(self):
        self._reserve()

        self.assertEqual(budget.purge_expired_public_assistant_budgets(), 0)
        self.assertEqual(PublicAssistantTokenBudget.objects.count(), 2)

    def test_purge_removes_an_expired_global_row_and_the_next_request_recreates_it(self):
        reservation = self._reserve()
        PublicAssistantTokenBudget.objects.update(window_expires_at=timezone.now() - timedelta(seconds=1))

        self.assertEqual(budget.purge_expired_public_assistant_budgets(), 2)
        # A settlement arriving after the purge finds nothing to adjust.
        budget.reconcile_budget(reservation, 80)
        self.assertFalse(PublicAssistantTokenBudget.objects.exists())

        self.assertIsNotNone(self._reserve(amount=40))
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 40)

    def test_database_failure_is_reported_as_backend_unavailable(self):
        with patch.object(budget, "_locked_database_budget", side_effect=RuntimeError("db down")):
            with self.assertRaises(budget.BudgetBackendUnavailable):
                self._reserve()

        self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    # ----- one global row per feature -------------------------------------

    def test_global_keys_are_fixed_and_distinct(self):
        # The keys are primary keys of live rows: changing one silently starts
        # that feature on a fresh, empty budget.
        self.assertEqual(
            ASSISTANT_GLOBAL_KEY,
            hashlib.sha256(b"public-assistant:global-budget:assistant").hexdigest(),
        )
        self.assertEqual(
            AI_SEARCH_GLOBAL_KEY,
            hashlib.sha256(b"public-assistant:global-budget:ai-search").hexdigest(),
        )
        self.assertNotEqual(ASSISTANT_GLOBAL_KEY, AI_SEARCH_GLOBAL_KEY)
        self.assertEqual(set(budget.GLOBAL_BUDGET_KEYS), {ASSISTANT, AI_SEARCH})
        self.assertEqual(budget.global_budget_key(AI_SEARCH), AI_SEARCH_GLOBAL_KEY)

    def test_each_feature_is_charged_to_its_own_global_row(self):
        chat = self._reserve(self.actor, amount=150, feature=ASSISTANT)
        search = self._reserve(self.other, amount=70, feature=AI_SEARCH)

        self.assertEqual(chat.global_reservation.actor_key, ASSISTANT_GLOBAL_KEY)
        self.assertEqual(search.global_reservation.actor_key, AI_SEARCH_GLOBAL_KEY)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 150)
        self.assertEqual(budget.global_tokens_used(AI_SEARCH), 70)
        self.assertEqual(
            set(PublicAssistantTokenBudget.objects.values_list("pk", flat=True)),
            {self.actor, self.other, ASSISTANT_GLOBAL_KEY, AI_SEARCH_GLOBAL_KEY},
        )
        self.assertEqual(PublicAssistantTokenReservation.objects.count(), 4)

    def test_a_feature_never_creates_the_other_features_global_row(self):
        self._reserve(feature=AI_SEARCH)

        self.assertEqual(
            set(PublicAssistantTokenBudget.objects.values_list("pk", flat=True)),
            {self.actor, AI_SEARCH_GLOBAL_KEY},
        )

    def test_draining_the_assistant_budget_does_not_pause_ai_search(self):
        # An anonymous script: every request under a freshly minted identity,
        # so no per-actor limit ever binds and only the global row stops it.
        with self.assertLogs(BUDGET_LOGGER, level="WARNING") as logs:
            admitted = [
                self._reserve(budget.hash_ip(f"minted-{index}"), amount=100, limit=150, feature=ASSISTANT)
                for index in range(60)
            ]

        self.assertEqual(sum(reservation is not None for reservation in admitted), 50)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 5000)
        self.assertEqual(len(logs.output), 1)
        self.assertIn("global token budget exhausted for Public assistant", logs.output[0])

        # A member's AI search has the same limit but its own counter.
        with self.assertNoLogs(BUDGET_LOGGER, level="WARNING"):
            search = self._reserve(self.other, amount=4000, feature=AI_SEARCH)

        self.assertIsNotNone(search)
        self.assertEqual(search.global_reservation.actor_key, AI_SEARCH_GLOBAL_KEY)
        self.assertEqual(budget.global_tokens_used(AI_SEARCH), 4000)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 5000)

    def test_draining_ai_search_does_not_pause_the_assistant(self):
        self.assertIsNotNone(self._reserve(self.other, amount=5000, feature=AI_SEARCH))
        with self.assertLogs(BUDGET_LOGGER, level="WARNING") as logs:
            self.assertIsNone(self._reserve(self.other, amount=1, feature=AI_SEARCH))

        self.assertIn("global token budget exhausted for AI search", logs.output[0])
        self.assertIsNotNone(self._reserve(self.actor, amount=5000, feature=ASSISTANT))
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 5000)
        self.assertEqual(budget.global_tokens_used(AI_SEARCH), 5000)

    def test_one_actor_using_both_features_has_one_row_and_two_global_charges(self):
        chat = self._reserve(self.actor, amount=150, limit=1000, feature=ASSISTANT)
        search = self._reserve(self.actor, amount=70, limit=1000, feature=AI_SEARCH)

        # The per-actor limit still spans both features.
        self.assertEqual(budget.tokens_used(self.actor), 220)
        self.assertIsNone(self._reserve(self.actor, amount=781, limit=1000, feature=AI_SEARCH))

        budget.reconcile_budget(chat, 80)
        budget.release_budget(search)

        self.assertEqual(budget.tokens_used(self.actor), 80)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 80)
        self.assertEqual(budget.global_tokens_used(AI_SEARCH), 0)
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    def test_each_feature_logs_its_own_exhaustion_once_a_minute(self):
        self._reserve(self.other, amount=4900, feature=ASSISTANT)
        self._reserve(self.other, amount=4900, feature=AI_SEARCH)

        with self.assertLogs(BUDGET_LOGGER, level="WARNING") as logs:
            for _ in range(3):
                self.assertIsNone(self._reserve(amount=150, feature=ASSISTANT))
                self.assertIsNone(self._reserve(amount=150, feature=AI_SEARCH))

        self.assertEqual(len(logs.output), 2)
        self.assertIn("global token budget exhausted for Public assistant (limit 5000 per 86400s)", logs.output[0])
        self.assertIn("global token budget exhausted for AI search (limit 5000 per 86400s)", logs.output[1])

    def test_zero_global_limit_switches_off_either_feature_without_rows(self):
        for feature in (ASSISTANT, AI_SEARCH):
            with self.subTest(feature=feature), self.assertNoLogs(BUDGET_LOGGER, level="WARNING"):
                self.assertIsNone(self._reserve(amount=1, limit=0, global_limit=0, feature=feature))

        self.assertFalse(PublicAssistantTokenBudget.objects.exists())

    def test_a_global_limit_needs_a_known_feature(self):
        for feature in (None, "", "chat", ["assistant"]):
            for global_limit in (5000, 0):
                with self.subTest(feature=feature, global_limit=global_limit), self.assertRaises(ValueError):
                    self._reserve(feature=feature, global_limit=global_limit)
        with self.assertRaises(ValueError):
            budget.global_tokens_used("chat")

        self.assertFalse(PublicAssistantTokenBudget.objects.exists())
        # Without global accounting there is nothing to name.
        self.assertIsNotNone(self._reserve(global_limit=None, feature=None))

    # ----- usage read-out (shown in Django admin) --------------------------

    def test_global_usage_read_out_reports_both_features(self):
        self.assertEqual(
            [
                (entry.feature, entry.label, entry.tokens_used, entry.window_expires_at)
                for entry in budget.global_budget_usage()
            ],
            [(ASSISTANT, "Public assistant", 0, None), (AI_SEARCH, "AI search", 0, None)],
        )
        before = timezone.now()
        self._reserve(self.actor, amount=150, feature=ASSISTANT)
        budget.reconcile_budget(self._reserve(self.other, amount=70, feature=AI_SEARCH), 30)

        chat, search = budget.global_budget_usage()

        self.assertEqual((chat.feature, chat.tokens_used), (ASSISTANT, 150))
        self.assertEqual((search.feature, search.tokens_used), (AI_SEARCH, 30))
        for entry in (chat, search):
            self.assertGreaterEqual(entry.window_expires_at, before + timedelta(hours=24))
            self.assertLessEqual(entry.window_expires_at, timezone.now() + timedelta(hours=24))

    def test_global_usage_read_out_ignores_an_expired_window(self):
        self._reserve(self.actor, amount=150, feature=ASSISTANT)
        self._reserve(self.actor, amount=70, feature=AI_SEARCH)
        PublicAssistantTokenBudget.objects.filter(pk=ASSISTANT_GLOBAL_KEY).update(
            window_expires_at=timezone.now() - timedelta(seconds=1),
        )

        chat, search = budget.global_budget_usage()

        self.assertEqual((chat.tokens_used, chat.window_expires_at), (0, None))
        self.assertEqual(search.tokens_used, 70)

    def test_global_usage_read_out_is_one_query_and_locks_nothing(self):
        self._reserve(self.actor, amount=150, feature=ASSISTANT)

        # SQLite never emits FOR UPDATE, so also refuse the ORM call itself.
        with (
            patch.object(QuerySet, "select_for_update", side_effect=AssertionError("the read-out must not lock")),
            CaptureQueriesContext(connection) as captured,
        ):
            budget.global_budget_usage()

        self.assertEqual(len(captured), 1)
        self.assertNotIn("FOR UPDATE", captured[0]["sql"].upper())
        # Reading creates nothing.
        self.assertFalse(PublicAssistantTokenBudget.objects.filter(pk=AI_SEARCH_GLOBAL_KEY).exists())

    # ----- provider usage that is not a number ------------------------------

    def test_unparsable_provider_usage_settles_the_reservation_at_the_reserved_amount(self):
        for value in ("x", "12 tokens", float("nan"), float("inf"), object(), [80], {"totalTokens": 80}):
            with self.subTest(value=repr(value)):
                PublicAssistantTokenBudget.objects.all().delete()
                reservation = self._reserve(amount=150)

                with self.assertLogs(BUDGET_LOGGER, level="WARNING") as logs:
                    budget.reconcile_budget(reservation, value)

                # Charged as reserved on both levels, and the reservation is consumed.
                self.assertEqual(budget.tokens_used(self.actor), 150)
                self.assertEqual(budget.global_tokens_used(ASSISTANT), 150)
                self.assertFalse(PublicAssistantTokenReservation.objects.exists())
                self.assertEqual(len(logs.output), 1)
                self.assertIn("Unparsable provider token usage", logs.output[0])
                self.assertIn("charging the reserved 150 tokens", logs.output[0])

    def test_an_absurdly_large_reported_total_is_treated_as_unreadable(self):
        """A number no call can cost would overflow the counters; the call is settled at the reserved amount."""
        for value in (budget.MAX_REPORTED_TOKENS + 1, 10**30, True):
            with self.subTest(value=value):
                PublicAssistantTokenBudget.objects.all().delete()
                reservation = self._reserve(amount=150)

                with self.assertLogs(BUDGET_LOGGER, level="WARNING"):
                    budget.reconcile_budget(reservation, value)

                self.assertEqual(budget.tokens_used(self.actor), 150)
                self.assertEqual(budget.global_tokens_used(ASSISTANT), 150)
                self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    def test_the_largest_plausible_total_and_zero_are_charged_as_reported(self):
        for value, expected in ((0, 0), (None, 0), (-5, 0), ("80", 80), (80.9, 80)):
            with self.subTest(value=value):
                PublicAssistantTokenBudget.objects.all().delete()
                reservation = self._reserve(amount=150)

                budget.reconcile_budget(reservation, value)

                self.assertEqual(budget.tokens_used(self.actor), expected)
                self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    def test_sanitized_usage_keeps_only_plausible_token_counts(self):
        self.assertEqual(
            budget.sanitized_usage({"inputTokens": 5, "outputTokens": "7", "totalTokens": 12.0, "extra": "x"}),
            {"inputTokens": 5, "outputTokens": 7, "totalTokens": 12},
        )
        self.assertEqual(
            budget.sanitized_usage({"inputTokens": float("nan"), "outputTokens": float("inf"), "totalTokens": 10**30}),
            {},
        )
        self.assertEqual(budget.sanitized_usage({"inputTokens": -1, "outputTokens": True, "totalTokens": None}), {})
        for not_a_mapping in (None, "x", [1], 5):
            self.assertEqual(budget.sanitized_usage(not_a_mapping), {})

    def test_reported_total_tokens_passes_an_unreadable_block_through_to_reconciliation(self):
        self.assertEqual(budget.reported_total_tokens({"totalTokens": 42}), 42)
        self.assertEqual(budget.reported_total_tokens({}), 0)
        self.assertEqual(budget.reported_total_tokens(None), 0)
        # Not a mapping: reconciliation must see it and charge the reserved amount, not zero.
        self.assertEqual(budget.reported_total_tokens(["x"]), ["x"])
        self.assertEqual(budget.reported_total_tokens("garbage"), "garbage")

    def test_unparsable_provider_usage_is_not_echoed_at_length_into_the_log(self):
        reservation = self._reserve(amount=150)

        with self.assertLogs(BUDGET_LOGGER, level="WARNING") as logs:
            budget.reconcile_budget(reservation, "z" * 100_000)

        self.assertLess(len(logs.output[0]), 400)

    def test_number_like_provider_usage_is_reconciled_as_a_number(self):
        for value, expected in (("80", 80), (80.9, 80), (None, 0), (0, 0), (-500, 0), ("", 0)):
            with self.subTest(value=value):
                PublicAssistantTokenBudget.objects.all().delete()
                reservation = self._reserve(amount=150)

                with self.assertNoLogs(BUDGET_LOGGER, level="WARNING"):
                    budget.reconcile_budget(reservation, value)

                self.assertEqual(budget.tokens_used(self.actor), expected)
                self.assertEqual(budget.global_tokens_used(ASSISTANT), expected)
                self.assertFalse(PublicAssistantTokenReservation.objects.exists())


@override_settings(PUBLIC_ASSISTANT_ALLOW_LOCAL_BUDGET=False, REDIS_URL="")
class DatabaseBudgetConcurrencyTests(TransactionTestCase):
    @skipUnlessDBFeature("has_select_for_update")
    def test_first_reservations_from_separate_connections_do_not_overspend(self):
        ip_hash = budget.hash_ip("203.0.113.22")
        ready = Barrier(2)

        def reserve(_index):
            close_old_connections()
            try:
                ready.wait(timeout=5)
                return (
                    budget.reserve_budget(
                        ip_hash,
                        estimated_input_tokens=60,
                        maximum_output_tokens=0,
                        limit=100,
                        window_seconds=3600,
                    )
                    is not None
                )
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            accepted = list(executor.map(reserve, range(2)))

        self.assertEqual(sum(accepted), 1)
        self.assertEqual(budget.tokens_used(ip_hash), 60)
        self.assertEqual(PublicAssistantTokenReservation.objects.count(), 1)

    @skipUnlessDBFeature("has_select_for_update", "has_select_for_update_skip_locked")
    def test_cleanup_skips_a_budget_being_reactivated(self):
        ip_hash = budget.hash_ip("203.0.113.23")
        PublicAssistantTokenBudget.objects.create(
            ip_hash=ip_hash,
            window_id=budget._new_window_id(),
            tokens_used=25,
            window_expires_at=timezone.now() - timedelta(seconds=1),
        )
        locked = Event()
        release_lock = Event()

        def reactivate():
            close_old_connections()
            try:
                with transaction.atomic():
                    state = PublicAssistantTokenBudget.objects.select_for_update().get(pk=ip_hash)
                    state.window_id = budget._new_window_id()
                    state.tokens_used = 60
                    state.window_expires_at = timezone.now() + timedelta(hours=1)
                    state.save()
                    locked.set()
                    if not release_lock.wait(timeout=5):
                        raise TimeoutError("test did not release the budget row lock")
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(reactivate)
            self.assertTrue(locked.wait(timeout=5))
            try:
                self.assertEqual(budget.purge_expired_public_assistant_budgets(), 0)
            finally:
                release_lock.set()
            future.result(timeout=5)

        state = PublicAssistantTokenBudget.objects.get(pk=ip_hash)
        self.assertEqual(state.tokens_used, 60)
        self.assertGreater(state.window_expires_at, timezone.now())

    @skipUnlessDBFeature("has_select_for_update")
    def test_concurrent_actors_cannot_overspend_the_global_budget(self):
        # 8 different actors race for a global budget that fits exactly 3 of
        # them; every per-actor limit is far away. Only the global row lock can
        # serialise them.
        workers = 8
        ready = Barrier(workers)

        def reserve(index):
            close_old_connections()
            try:
                ready.wait(timeout=10)
                return (
                    budget.reserve_budget(
                        budget.hash_ip(f"concurrent-actor-{index}"),
                        estimated_input_tokens=60,
                        maximum_output_tokens=0,
                        limit=1000,
                        window_seconds=3600,
                        global_limit=200,
                        feature=ASSISTANT,
                    )
                    is not None
                )
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=workers) as executor:
            accepted = list(executor.map(reserve, range(workers)))

        self.assertEqual(sum(accepted), 3)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 180)
        # One global + one actor reservation per admitted request, none for the refused.
        self.assertEqual(PublicAssistantTokenReservation.objects.count(), 6)
        self.assertEqual(PublicAssistantTokenBudget.objects.exclude(pk=ASSISTANT_GLOBAL_KEY).count(), 3)

    @skipUnlessDBFeature("has_select_for_update")
    def test_concurrent_reserve_and_settle_do_not_deadlock_or_leak(self):
        # Reserve and settle both take the global row lock and then the actor
        # row lock. Half the workers share ONE actor row, so both locks are
        # contended at once; an inconsistent order would make PostgreSQL abort
        # one transaction with "deadlock detected" (surfacing here as
        # BudgetBackendUnavailable).
        workers, rounds, actual = 6, 10, 7
        shared_actor = budget.hash_ip("churn-shared")
        ready = Barrier(workers)

        def churn(index):
            close_old_connections()
            try:
                actor = shared_actor if index % 2 else budget.hash_ip(f"churn-{index}")
                ready.wait(timeout=10)
                for round_number in range(rounds):
                    reservation = budget.reserve_budget(
                        actor,
                        estimated_input_tokens=10,
                        maximum_output_tokens=0,
                        limit=0,
                        window_seconds=3600,
                        global_limit=1_000_000,
                        feature=ASSISTANT,
                    )
                    if round_number % 2:
                        budget.release_budget(reservation)
                    else:
                        budget.reconcile_budget(reservation, actual)
                return True
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(churn, index) for index in range(workers)]
            completed = [future.result(timeout=60) for future in futures]

        self.assertEqual(completed, [True] * workers)
        reconciled_rounds = (rounds + 1) // 2
        self.assertEqual(budget.global_tokens_used(ASSISTANT), workers * reconciled_rounds * actual)
        self.assertEqual(budget.tokens_used(shared_actor), (workers // 2) * reconciled_rounds * actual)
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    @skipUnlessDBFeature("has_select_for_update")
    def test_both_features_charging_one_member_do_not_deadlock_or_leak(self):
        # A member chatting and searching at once: the two features lock
        # DIFFERENT global rows and then the SAME actor row. Nobody who holds
        # the actor row waits for another budget row, so PostgreSQL must never
        # report "deadlock detected" (it would surface here as
        # BudgetBackendUnavailable), and every charge must be settled.
        workers, rounds, actual = 6, 10, 7
        shared_actor = budget.hash_ip("both-features-member")
        ready = Barrier(workers)

        def churn(index):
            close_old_connections()
            try:
                feature = ASSISTANT if index % 2 else AI_SEARCH
                ready.wait(timeout=10)
                for round_number in range(rounds):
                    reservation = budget.reserve_budget(
                        shared_actor,
                        estimated_input_tokens=10,
                        maximum_output_tokens=0,
                        limit=0,
                        window_seconds=3600,
                        global_limit=1_000_000,
                        feature=feature,
                    )
                    if round_number % 2:
                        budget.release_budget(reservation)
                    else:
                        budget.reconcile_budget(reservation, actual)
                return True
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(churn, index) for index in range(workers)]
            completed = [future.result(timeout=60) for future in futures]

        self.assertEqual(completed, [True] * workers)
        reconciled_rounds = (rounds + 1) // 2
        per_feature = (workers // 2) * reconciled_rounds * actual
        self.assertEqual(budget.global_tokens_used(ASSISTANT), per_feature)
        self.assertEqual(budget.global_tokens_used(AI_SEARCH), per_feature)
        self.assertEqual(budget.tokens_used(shared_actor), 2 * per_feature)
        self.assertFalse(PublicAssistantTokenReservation.objects.exists())

    @skipUnlessDBFeature("has_select_for_update")
    def test_a_concurrent_drain_of_the_assistant_never_refuses_ai_search(self):
        # 8 anonymous actors race for an assistant budget that fits exactly 3
        # of them while 2 members search. The limit is the same number for
        # both features, but each has its own row: both searches are admitted.
        chat_workers, search_workers = 8, 2
        ready = Barrier(chat_workers + search_workers)

        def reserve(index):
            close_old_connections()
            try:
                feature = ASSISTANT if index < chat_workers else AI_SEARCH
                ready.wait(timeout=10)
                reservation = budget.reserve_budget(
                    budget.hash_ip(f"isolation-actor-{index}"),
                    estimated_input_tokens=60,
                    maximum_output_tokens=0,
                    limit=1000,
                    window_seconds=3600,
                    global_limit=200,
                    feature=feature,
                )
                return feature, reservation is not None
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=chat_workers + search_workers) as executor:
            outcomes = list(executor.map(reserve, range(chat_workers + search_workers)))

        self.assertEqual(sum(admitted for feature, admitted in outcomes if feature == ASSISTANT), 3)
        self.assertEqual(sum(admitted for feature, admitted in outcomes if feature == AI_SEARCH), 2)
        self.assertEqual(budget.global_tokens_used(ASSISTANT), 180)
        self.assertEqual(budget.global_tokens_used(AI_SEARCH), 120)


@override_settings(PUBLIC_ASSISTANT_ALLOW_LOCAL_BUDGET=False, REDIS_URL="redis://configured")
class RedisReservationScriptTests(TestCase):
    def setUp(self):
        # Redis is mocked here, but the once-a-minute global-exhaustion warning is deduplicated in the Django
        # cache, so a key left by an earlier test that hit that warning would silence the one asserted below.
        cache.clear()

    @patch.object(budget, "_shared_redis_client")
    def test_reservation_uses_remaining_budget_window_ttl(self, redis_connection):
        redis_client = Mock()
        redis_client.eval.return_value = 150
        redis_connection.return_value = redis_client

        reservation = budget.reserve_budget(
            budget.hash_ip("203.0.113.9"),
            estimated_input_tokens=100,
            maximum_output_tokens=50,
            limit=1000,
            window_seconds=60,
        )

        self.assertIsNotNone(reservation)
        reserve_args = redis_client.eval.call_args.args
        self.assertIs(reserve_args[0], budget._RESERVE_SCRIPT)
        self.assertEqual(reserve_args[1], 3)
        self.assertEqual(reserve_args[2], reservation.budget_cache_key)
        self.assertEqual(reserve_args[3], reservation.window_cache_key)
        self.assertEqual(reserve_args[4], reservation.reservation_cache_key)
        self.assertEqual(reserve_args[5:8], (150, 1000, 60_000))
        self.assertIn("budget_ttl = redis.call('PTTL', KEYS[1])", budget._RESERVE_SCRIPT)
        self.assertIn(
            "redis.call('PSETEX', KEYS[3], budget_ttl",
            budget._RESERVE_SCRIPT,
        )

    def test_missing_redis_backend_is_reported_as_backend_unavailable(self):
        # REDIS_URL is configured but no Redis-backed cache is reachable, and the
        # local fallback is off: fail closed instead of silently not budgeting.
        with self.assertRaises(budget.BudgetBackendUnavailable):
            budget._shared_redis_client()

    def test_reconcile_and_release_require_the_original_window(self):
        for script in (budget._RECONCILE_SCRIPT, budget._RELEASE_SCRIPT):
            self.assertIn("active_window_id ~= reservation_window_id", script)
            self.assertIn("redis.call('EXISTS', KEYS[1]) == 0", script)
            guard_position = script.index("active_window_id ~= reservation_window_id")
            mutation_position = script.index("redis.call('INCRBY', KEYS[1]")
            self.assertLess(guard_position, mutation_position)

    @patch.object(budget, "_shared_redis_client")
    def test_two_level_redis_reservation_charges_global_then_actor(self, redis_connection):
        redis_client = Mock()
        redis_client.eval.return_value = 150
        redis_connection.return_value = redis_client
        actor = budget.hash_ip("203.0.113.9")

        reservation = budget.reserve_budget(
            actor,
            estimated_input_tokens=100,
            maximum_output_tokens=50,
            limit=1000,
            window_seconds=60,
            global_limit=5000,
            feature=ASSISTANT,
        )

        global_call, actor_call = (call.args for call in redis_client.eval.call_args_list)
        self.assertEqual(global_call[2], cache.make_key(budget.budget_key(ASSISTANT_GLOBAL_KEY)))
        self.assertEqual(global_call[5:8], (150, 5000, budget.GLOBAL_WINDOW_SECONDS * 1000))
        self.assertEqual(actor_call[2], cache.make_key(budget.budget_key(actor)))
        self.assertEqual(actor_call[5:8], (150, 1000, 60_000))
        self.assertEqual(reservation.global_reservation.budget_cache_key, global_call[2])

        redis_client.eval.reset_mock()
        budget.reconcile_budget(reservation, 80)

        scripts = [call.args[0] for call in redis_client.eval.call_args_list]
        self.assertEqual(scripts, [budget._RECONCILE_SCRIPT, budget._RECONCILE_SCRIPT])
        settled_keys = {call.args[2] for call in redis_client.eval.call_args_list}
        self.assertEqual(settled_keys, {global_call[2], actor_call[2]})

    @patch.object(budget, "_shared_redis_client")
    def test_redis_reservation_charges_the_global_counter_of_its_feature(self, redis_connection):
        actor = budget.hash_ip("203.0.113.9")
        for feature, global_key in ((ASSISTANT, ASSISTANT_GLOBAL_KEY), (AI_SEARCH, AI_SEARCH_GLOBAL_KEY)):
            with self.subTest(feature=feature):
                redis_client = Mock()
                redis_client.eval.return_value = 150
                redis_connection.return_value = redis_client

                reservation = budget.reserve_budget(
                    actor,
                    estimated_input_tokens=100,
                    maximum_output_tokens=50,
                    limit=1000,
                    window_seconds=60,
                    global_limit=5000,
                    feature=feature,
                )

                global_call = redis_client.eval.call_args_list[0].args
                self.assertEqual(global_call[2], cache.make_key(budget.budget_key(global_key)))
                self.assertEqual(reservation.global_reservation.actor_key, global_key)

    @patch.object(budget, "_shared_redis_client")
    def test_redis_actor_refusal_or_failure_returns_the_global_charge(self, redis_connection):
        actor = budget.hash_ip("203.0.113.9")
        for label, actor_step, expected in (
            ("refused", -1, None),
            ("backend failure", RuntimeError("redis down"), budget.BudgetBackendUnavailable),
        ):
            with self.subTest(label):
                redis_client = Mock()
                # global reserve OK -> actor reserve refused/fails -> global release
                redis_client.eval.side_effect = [150, actor_step, 1]
                redis_connection.return_value = redis_client

                def reserve():
                    return budget.reserve_budget(
                        actor,
                        estimated_input_tokens=100,
                        maximum_output_tokens=50,
                        limit=1000,
                        window_seconds=60,
                        global_limit=5000,
                        feature=ASSISTANT,
                    )

                if expected is None:
                    self.assertIsNone(reserve())
                else:
                    with self.assertRaises(expected):
                        reserve()

                release_call = redis_client.eval.call_args_list[2].args
                self.assertIs(release_call[0], budget._RELEASE_SCRIPT)
                self.assertEqual(release_call[2], cache.make_key(budget.budget_key(ASSISTANT_GLOBAL_KEY)))

    @patch.object(budget, "_shared_redis_client")
    def test_redis_settlement_attempts_both_levels_even_if_one_fails(self, redis_connection):
        redis_client = Mock()
        redis_client.eval.return_value = 150
        redis_connection.return_value = redis_client
        reservation = budget.reserve_budget(
            budget.hash_ip("203.0.113.9"),
            estimated_input_tokens=100,
            maximum_output_tokens=50,
            limit=1000,
            window_seconds=60,
            global_limit=5000,
            feature=ASSISTANT,
        )
        redis_client.eval.reset_mock()
        redis_client.eval.side_effect = [RuntimeError("blip"), 1]

        with self.assertRaises(budget.BudgetBackendUnavailable):
            budget.release_budget(reservation)

        self.assertEqual(redis_client.eval.call_count, 2)

    @patch.object(budget, "_shared_redis_client")
    def test_single_level_redis_failure_is_reported_as_backend_unavailable(self, redis_connection):
        redis_client = Mock()
        redis_client.eval.side_effect = RuntimeError("redis down")
        redis_connection.return_value = redis_client

        with self.assertRaises(budget.BudgetBackendUnavailable):
            budget.reserve_budget(
                budget.hash_ip("203.0.113.9"),
                estimated_input_tokens=100,
                maximum_output_tokens=50,
                limit=1000,
                window_seconds=60,
            )

        self.assertEqual(redis_client.eval.call_count, 1)

    @patch.object(budget, "_shared_redis_client")
    def test_failing_to_return_the_global_charge_is_logged_not_raised(self, redis_connection):
        redis_client = Mock()
        # global reserve OK -> actor refused -> returning the global charge fails
        redis_client.eval.side_effect = [150, -1, RuntimeError("redis down")]
        redis_connection.return_value = redis_client

        with self.assertLogs("apps.system_intelligence.services.public_assistant.budget", level="ERROR") as logs:
            reservation = budget.reserve_budget(
                budget.hash_ip("203.0.113.9"),
                estimated_input_tokens=100,
                maximum_output_tokens=50,
                limit=1000,
                window_seconds=60,
                global_limit=5000,
                feature=ASSISTANT,
            )

        self.assertIsNone(reservation)
        self.assertIn("Could not return an unused global assistant reservation", logs.output[0])

    @patch.object(budget, "_shared_redis_client")
    def test_redis_global_refusal_never_touches_the_actor_counter(self, redis_connection):
        redis_client = Mock()
        redis_client.eval.return_value = -1
        redis_connection.return_value = redis_client

        with self.assertLogs("apps.system_intelligence.services.public_assistant.budget", level="WARNING"):
            reservation = budget.reserve_budget(
                budget.hash_ip("203.0.113.9"),
                estimated_input_tokens=100,
                maximum_output_tokens=50,
                limit=1000,
                window_seconds=60,
                global_limit=5000,
                feature=ASSISTANT,
            )

        self.assertIsNone(reservation)
        self.assertEqual(redis_client.eval.call_count, 1)
