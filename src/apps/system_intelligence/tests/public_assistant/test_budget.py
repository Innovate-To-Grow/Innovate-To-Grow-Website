"""Unit tests for the per-IP token budget helpers."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Event
from unittest.mock import Mock, patch

from django.core.cache import cache
from django.db import close_old_connections, transaction
from django.test import RequestFactory, TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.utils import timezone

from apps.system_intelligence.models import PublicAssistantTokenBudget, PublicAssistantTokenReservation
from apps.system_intelligence.services.public_assistant import budget


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


@override_settings(PUBLIC_ASSISTANT_ALLOW_LOCAL_BUDGET=False, REDIS_URL="redis://configured")
class RedisReservationScriptTests(TestCase):
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

    def test_reconcile_and_release_require_the_original_window(self):
        for script in (budget._RECONCILE_SCRIPT, budget._RELEASE_SCRIPT):
            self.assertIn("active_window_id ~= reservation_window_id", script)
            self.assertIn("redis.call('EXISTS', KEYS[1]) == 0", script)
            guard_position = script.index("active_window_id ~= reservation_window_id")
            mutation_position = script.index("redis.call('INCRBY', KEYS[1]")
            self.assertLess(guard_position, mutation_position)
