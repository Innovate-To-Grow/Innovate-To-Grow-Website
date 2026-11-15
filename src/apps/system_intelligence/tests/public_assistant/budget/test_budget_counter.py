from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.system_intelligence.services.public_assistant import budget


class _BudgetCounterCase(TestCase):
    def setUp(self):
        cache.clear()
        self.ip_hash = budget.hash_ip("198.51.100.4")

    def _reserve_150(self):
        return budget.reserve_budget(
            self.ip_hash,
            estimated_input_tokens=100,
            maximum_output_tokens=50,
            limit=1000,
            window_seconds=86400,
        )

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


@override_settings(PUBLIC_ASSISTANT_ALLOW_LOCAL_BUDGET=True)
class BudgetCounterTests(_BudgetCounterCase):
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
