"""The middleware end to end: the 429 contract with CORS, per-caller and aggregate limits, exemptions, the off
switch, unmatched paths, abuse escalation from the view's own refusals, per-process division and fail-open."""

import copy
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.models import RequestLimitProcess, RequestRateLimitPolicy
from apps.core.services.request_limits import limiter
from apps.core.services.request_limits.runtime import heartbeat, signals
from apps.core.services.request_limits.runtime.context import as_datetime

from .helpers import START, TEST_SCOPES, isolate, limiter_on, limits_with

Member = get_user_model()
URLS = "apps.core.tests.request_limits.urls"


def scopes_with(**changes):
    scopes = copy.deepcopy(TEST_SCOPES)
    for name, values in changes.items():
        scopes.setdefault(name, copy.deepcopy(TEST_SCOPES["t-p1"])).update(values)
    return override_settings(REQUEST_RATE_LIMITS=limits_with(scopes=scopes))


@limiter_on()
class MiddlewareTests(TestCase):
    def setUp(self):
        cache.clear()
        self.clock = isolate(self)
        self.client = APIClient()
        self.member = Member.objects.create_user(email="mw@example.com", password="pw-123456!", is_active=True)
        self.token = str(RefreshToken.for_user(self.member).access_token)

    def as_member(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")

    @override_settings(CORS_ALLOWED_ORIGINS=["http://front.test"])
    def test_the_429_contract_carries_cors_headers(self):
        self.as_member()
        statuses = [self.client.get("/p0/", HTTP_ORIGIN="http://front.test").status_code for _ in range(5)]
        self.assertEqual(statuses, [200] * 5)
        self.clock.advance(15)
        response = self.client.get("/p0/", HTTP_ORIGIN="http://front.test")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(
            response.json(),
            {"detail": "Too many requests. Please try again in 45 seconds.", "code": "rate_limited", "retry_after": 45},
        )
        self.assertEqual((response["Retry-After"], response["Cache-Control"]), ("45", "no-store"))
        self.assertEqual(response["Access-Control-Allow-Origin"], "http://front.test")
        self.assertIn("Retry-After", response["Access-Control-Expose-Headers"])

    def test_one_second_is_singular(self):
        body = json.loads(limiter.rejection(0.2).content)
        self.assertEqual(body["detail"], "Too many requests. Please try again in 1 second.")

    def test_each_member_has_its_own_bucket_and_the_window_resets(self):
        self.as_member()
        for _ in range(5):
            self.client.get("/p0/")
        self.assertEqual(self.client.get("/p0/").status_code, 429)
        other = Member.objects.create_user(email="other@example.com", password="pw-123456!", is_active=True)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(other).access_token}")
        self.assertEqual(self.client.get("/p0/").status_code, 200)
        self.as_member()
        self.clock.advance(60)
        self.assertEqual(self.client.get("/p0/").status_code, 200)

    def test_anonymous_callers_of_a_member_scope_share_only_the_aggregate_cap(self):
        with scopes_with(**{"t-p0": {"global_cap": 7}}):
            statuses = [self.client.get("/p0/", REMOTE_ADDR=f"10.0.0.{index}").status_code for index in range(9)]
        self.assertEqual(statuses, [200] * 7 + [429, 429])

    def test_ip_scopes_count_per_address(self):
        with scopes_with(**{"t-p1": {"requests": 2}}):
            first = [self.client.get("/p1/", REMOTE_ADDR="10.0.0.1").status_code for _ in range(3)]
            second = self.client.get("/p1/", REMOTE_ADDR="10.0.0.2").status_code
        self.assertEqual((first, second), ([200, 200, 429], 200))

    def test_a_method_map(self):
        with scopes_with(**{"t-p3": {"requests": 1}}):
            self.assertEqual([self.client.post("/methods/").status_code for _ in range(2)], [200, 429])
            self.assertEqual(self.client.get("/methods/").status_code, 200)

    def test_exemptions_and_preflights_are_never_limited(self):
        with scopes_with(**{"public-read": {"requests": 1}, "t-p1": {"requests": 1}}):
            self.assertEqual({self.client.get("/exempt/").status_code for _ in range(5)}, {200})
            self.assertEqual({self.client.options("/p1/").status_code for _ in range(5)}, {200})

    def test_a_disabled_policy_is_not_limited(self):
        with scopes_with(**{"t-p1": {"requests": 1}}):
            RequestRateLimitPolicy.for_scope("t-p1")
            RequestRateLimitPolicy.objects.filter(scope="t-p1").update(enabled=False)
            self.assertEqual({self.client.get("/p1/").status_code for _ in range(4)}, {200})

    def test_an_unknown_scope_is_not_limited(self):
        with patch("apps.core.tests.request_limits.urls.unscoped.rate_limit_scope", "nope", create=True):
            self.assertEqual(self.client.get("/unscoped/").status_code, 200)

    def test_the_fallback_scope_applies_to_an_unnamed_route(self):
        with scopes_with(**{"public-write": {"requests": 1}}):
            self.assertEqual([self.client.post("/unscoped/").status_code for _ in range(2)], [200, 429])

    def test_off_means_off(self):
        with override_settings(REQUEST_RATE_LIMITS_ENABLED=False), scopes_with(**{"t-p1": {"requests": 1}}):
            self.assertEqual({self.client.get("/p1/").status_code for _ in range(4)}, {200})
        self.assertFalse(signals.WINDOW.scopes)

    def test_unmatched_paths_are_limited_after_their_404(self):
        with scopes_with(**{"not-found": {**TEST_SCOPES["t-p3"], "requests": 3, "global_cap": None}}):
            statuses = [self.client.get(f"/missing-{index}/").status_code for index in range(5)]
            self.assertEqual(self.client.options("/missing/").status_code, 404)
            disabled = RequestRateLimitPolicy.objects.filter(scope="not-found")
            disabled.update(enabled=False)
            limiter.registry.invalidate()
            self.assertEqual(self.client.get("/missing-x/").status_code, 404)
        self.assertEqual(statuses, [404, 404, 404, 429, 429])
        self.assertEqual(signals.WINDOW.scopes["not-found"].limited, 2)

    def test_repeated_refusals_by_the_view_block_the_caller(self):
        self.as_member()
        with scopes_with(**{"t-p0": {"requests": 1_000}}):
            statuses = [self.client.post("/p0-refused/").status_code for _ in range(10)]
            blocked = self.client.get("/p0/")
            self.clock.advance(31)
            after = self.client.get("/p0/")
        self.assertEqual(statuses, [429] * 10)
        self.assertEqual((blocked.status_code, blocked.json()["retry_after"]), (429, 30))
        self.assertEqual(after.status_code, 200)

    def test_limits_are_divided_between_live_processes(self):
        RequestLimitProcess.objects.create(
            instance="other", pid=2, started_at=as_datetime(START), last_seen=as_datetime(START)
        )
        self.as_member()
        statuses = [self.client.get("/p0/").status_code for _ in range(4)]
        self.assertEqual(statuses, [200, 200, 200, 429])
        self.assertEqual(heartbeat.PROCESS.count, 2)

    def test_a_shared_store_is_not_divided(self):
        RequestLimitProcess.objects.create(
            instance="other", pid=2, started_at=as_datetime(START), last_seen=as_datetime(START)
        )
        self.as_member()
        with patch.object(limiter.store, "mode", return_value=limiter.store.SHARED):
            statuses = [self.client.get("/p0/").status_code for _ in range(6)]
        self.assertEqual(statuses, [200] * 5 + [429])
        self.assertFalse(RequestLimitProcess.objects.filter(instance=heartbeat.PROCESS.instance).exists())

    def test_signals_are_recorded_and_slots_released_even_when_the_view_raises(self):
        self.client.get("/p1/")
        self.client.get("/p1-error/")
        self.client.raise_request_exception = False
        self.assertEqual(self.client.get("/broken/").status_code, 500)
        window = signals.WINDOW.scopes["t-p1"]
        self.assertEqual((window.requests, window.errors), (2, 1))
        self.assertEqual(signals.WINDOW.scopes["public-read"].errors, 1)
        self.assertEqual(signals.in_flight(), 0)

    def test_an_exception_escaping_the_handler_releases_the_slot(self):
        middleware = limiter_middleware(lambda request: (_ for _ in ()).throw(RuntimeError("boom")))
        request = APIClient().get("/p1/").wsgi_request
        request._request_limit = limiter.Mark("t-p1", "p1", None, START, admitted=True)
        signals.INFLIGHT.count = 1
        with self.assertRaises(RuntimeError):
            middleware(request)
        self.assertEqual(signals.in_flight(), 0)

    def test_limiter_failures_fail_open(self):
        with (
            patch.object(limiter, "admit", side_effect=RuntimeError),
            self.assertLogs("apps.core.middleware.request_limits", "ERROR"),
        ):
            self.assertEqual(self.client.get("/p1/").status_code, 200)
        with (
            patch.object(limiter, "finish", side_effect=RuntimeError),
            self.assertLogs("apps.core.middleware.request_limits", "ERROR"),
        ):
            self.assertEqual(self.client.get("/p1/").status_code, 200)
        self.assertEqual(signals.in_flight(), 0)


def limiter_middleware(get_response):
    from apps.core.middleware import RequestRateLimitMiddleware

    return RequestRateLimitMiddleware(get_response)


@override_settings(REQUEST_RATE_LIMITS_ENABLED=True, ROOT_URLCONF=URLS)
class RealScopesTests(TestCase):
    """The shipped scopes through the real route table."""

    def setUp(self):
        cache.clear()
        isolate(self)
        self.client = APIClient()

    def test_robots_is_exempt_and_the_check_scope_is_per_member_only(self):
        with override_settings(ROOT_URLCONF="config.routing.urls"):
            self.assertEqual({self.client.get("/robots.txt").status_code for _ in range(3)}, {200})
            self.client.get("/authn/session/")
        self.assertIn("auth-session", signals.WINDOW.scopes)
