from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings

from apps.core.models import RequestRateLimitPolicy
from apps.core.services.request_limits import view_limits
from apps.core.services.request_limits.view_limits import (
    failure_lockout,
    record_failure,
)
from apps.core.tests.request_limits.routes.test_view_limits import ON, Ai, Member

from ..helpers import START, isolate, limits_with


class ThrottleBaseTests(TestCase):
    def setUp(self):
        cache.clear()
        isolate(self)
        self.factory = RequestFactory()

    def test_the_rate_is_read_per_instance(self):
        throttle = Ai()
        self.assertEqual((throttle.num_requests, throttle.duration), (10, 60))
        config = limits_with(scopes={})
        config["scopes"]["view-ai-search"] = {**config["scopes"]["view-ai-search"], "requests": 2}
        with override_settings(REQUEST_RATE_LIMITS=config):
            self.assertEqual(Ai().num_requests, 2)

    def test_a_disabled_policy_lets_every_request_through(self):
        with patch.object(view_limits, "view_rate", return_value=None):
            throttle = Ai()
        self.assertEqual((throttle.rate, throttle.num_requests, throttle.duration), (None, None, None))
        self.assertTrue(throttle.allow_request(self.factory.get("/"), None))

    def test_a_member_throttle_never_keys_an_anonymous_request_on_its_ip(self):
        request = self.factory.get("/", REMOTE_ADDR="10.0.0.1")
        request.user = AnonymousUser()
        self.assertIsNone(Member().get_cache_key(request, None))
        request.user = None
        self.assertIsNone(Member().get_cache_key(request, None))

    def test_a_member_throttle_keys_on_the_member(self):
        request = self.factory.get("/")
        request.user = SimpleNamespace(is_authenticated=True, pk="m-1")
        self.assertEqual(Member().get_cache_key(request, None), "throttle_test_member_m-1")

    def test_a_member_throttle_refuses_past_the_rate(self):
        config = limits_with(scopes={})
        config["scopes"]["view-code-verify"] = {**config["scopes"]["view-code-verify"], "requests": 2}
        request = self.factory.post("/")
        request.user = SimpleNamespace(is_authenticated=True, pk="m-2")
        with override_settings(REQUEST_RATE_LIMITS=config):
            results = [Member().allow_request(request, None) for _ in range(3)]
        self.assertEqual(results, [True, True, False])


class FailureLockoutTests(TestCase):
    def setUp(self):
        cache.clear()
        self.clock = isolate(self)
        config = limits_with(scopes={})
        config["scopes"]["view-maintenance-bypass"] = {
            **config["scopes"]["view-maintenance-bypass"],
            "requests": 3,
            "period_seconds": 60,
        }
        # The seed is the limit while the limiter is off; with it on the policy row would win.
        override = override_settings(REQUEST_RATE_LIMITS=config, REQUEST_RATE_LIMITS_ENABLED=False)
        override.enable()
        self.addCleanup(override.disable)

    def fail(self, times, bucket="*"):
        for _ in range(times):
            record_failure("view-maintenance-bypass", bucket)

    def test_locked_once_the_failures_are_used_up_until_the_window_ends(self):
        self.fail(2)
        self.assertIsNone(failure_lockout("view-maintenance-bypass"))
        self.fail(1)
        self.clock.advance(20)
        self.assertEqual(failure_lockout("view-maintenance-bypass"), 40)
        self.clock.advance(40)
        self.assertIsNone(failure_lockout("view-maintenance-bypass"))

    def test_buckets_are_independent(self):
        self.fail(3, "a")
        self.assertIsNotNone(failure_lockout("view-maintenance-bypass", "a"))
        self.assertIsNone(failure_lockout("view-maintenance-bypass", "b"))

    def test_a_disabled_policy_never_locks_and_counts_nothing(self):
        with patch.object(view_limits, "view_rate", return_value=None):
            self.fail(10)
            self.assertIsNone(failure_lockout("view-maintenance-bypass"))
        self.assertIsNone(failure_lockout("view-maintenance-bypass"))

    @ON
    def test_per_process_counters_allow_each_process_its_share(self):
        # The migrated row keeps the shipped period; the test seed is 3 per 60 s, so the row reads it at that period.
        RequestRateLimitPolicy.for_scope("view-maintenance-bypass")
        RequestRateLimitPolicy.objects.filter(scope="view-maintenance-bypass").update(period_seconds=60)
        with patch.object(view_limits, "live_processes", return_value=2):
            self.fail(2)
            self.assertIsNotNone(failure_lockout("view-maintenance-bypass"))

    @ON
    def test_a_shared_store_allows_the_whole_limit(self):
        self.fail(2)
        self.assertIsNone(failure_lockout("view-maintenance-bypass"))

    def test_the_clock_is_the_request_limit_clock(self):
        self.assertEqual(view_limits.context.clock(), START)
