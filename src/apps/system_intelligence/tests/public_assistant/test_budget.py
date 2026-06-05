"""Unit tests for the per-IP token budget helpers."""

from unittest.mock import patch

from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings

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
