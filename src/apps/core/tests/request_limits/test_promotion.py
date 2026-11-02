"""Priority promotion: a scope with a priority check stays P0 only for a request a person started (signed in, or the
check passes); anything else is counted in the unproven scope, which Smart limiting may shed and whose shared cap
never touches the promoted requests."""

from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.urls import resolve
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.checks import check_request_limits
from apps.core.models import RequestRateLimitPolicy
from apps.core.services.request_limits import priority, register_priority_check, scopes

from .helpers import TEST_SCOPES, isolate, limiter_on, limits_with, make_scope

Member = get_user_model()
URLS = "apps.core.tests.request_limits.urls"
UNPROVEN = "auth-code-unproven"


def keep_checks(test):
    saved = dict(priority._CHECKS)
    priority._CHECKS.clear()

    def restore():
        priority._CHECKS.clear()
        priority._CHECKS.update(saved)

    test.addCleanup(restore)


def has_proof(request):
    return request.headers.get("X-Proof") == "ok"


@override_settings(ROOT_URLCONF=URLS, REQUEST_RATE_LIMITS=limits_with())
class PromotionTests(TestCase):
    def setUp(self):
        cache.clear()
        isolate(self)
        keep_checks(self)
        self.factory = RequestFactory()

    def classify(self, path="/p0/", **extra):
        request = self.factory.post(path, **extra)
        request.resolver_match = resolve(path)
        return scopes.classify(request, request.resolver_match.func)

    def test_a_scope_without_a_check_is_never_demoted(self):
        self.assertEqual(self.classify(), scopes.Classification("t-p0", None, "view"))

    def test_without_proof_the_request_is_not_promoted(self):
        register_priority_check("t-p0", has_proof)
        self.assertEqual(self.classify(), scopes.Classification(UNPROVEN, None, "unproven"))

    def test_a_valid_proof_keeps_p0(self):
        register_priority_check("t-p0", has_proof)
        self.assertEqual(self.classify(HTTP_X_PROOF="ok").scope, "t-p0")

    def test_a_signed_in_person_is_promoted_without_running_the_check(self):
        check = Mock(return_value=False)
        register_priority_check("t-p0", check)
        request = self.factory.post("/p0/")
        request.resolver_match = resolve("/p0/")
        request._request_limit_identity = scopes.identity.Identity(member="m-1")
        self.assertEqual(scopes.classify(request, request.resolver_match.func).scope, "t-p0")
        check.assert_not_called()

    def test_a_check_given_by_its_dotted_path(self):
        register_priority_check("t-p0", f"{__name__}.has_proof")
        self.assertEqual(self.classify(HTTP_X_PROOF="ok").scope, "t-p0")
        self.assertEqual(self.classify().scope, UNPROVEN)

    def test_a_failing_check_is_not_a_promotion(self):
        register_priority_check("t-p0", Mock(side_effect=RuntimeError("boom")))
        with self.assertLogs("apps.core.services.request_limits.priority", level="WARNING"):
            self.assertEqual(self.classify().scope, UNPROVEN)

    def test_exemptions_and_preflights_are_untouched(self):
        register_priority_check("t-p0", has_proof)
        request = self.factory.options("/p0/", HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST")
        request.resolver_match = resolve("/p0/")
        self.assertEqual(scopes.classify(request, request.resolver_match.func).source, "preflight")

    def test_registered_checks_returns_a_copy(self):
        register_priority_check("t-p0", has_proof)
        found = priority.registered_checks()
        found.clear()
        self.assertEqual(priority.registered_checks(), {"t-p0": has_proof})

    def test_the_unproven_scope_is_p2_shared_with_a_flood_ceiling_per_source(self):
        spec = limits_with()["scopes"][UNPROVEN]
        self.assertEqual((spec["tier"], spec["identity"]), ("p2", "global"))
        self.assertIsNotNone(spec["global_cap"])
        self.assertLess(spec["source_cap"], spec["global_cap"])

    @override_settings(REQUEST_RATE_LIMITS_ENABLED=True)
    def test_a_check_for_an_unknown_scope_is_a_system_check_error(self):
        register_priority_check("nope", has_proof)
        self.assertEqual([problem.id for problem in check_request_limits()], ["core.E011"])


SCOPES = {**TEST_SCOPES, UNPROVEN: make_scope("p2", 100, identity="global", global_cap=2)}


@limiter_on(scopes=SCOPES)
class UnprovenTrafficTests(TestCase):
    """End to end: unproven floods use up only their own shared cap; proven and signed-in requests still pass."""

    def setUp(self):
        cache.clear()
        isolate(self)
        keep_checks(self)
        register_priority_check("t-p0", has_proof)
        # The seeded row is what the limiter reads: a cap of 2 for everyone without a proof.
        RequestRateLimitPolicy.objects.filter(scope=UNPROVEN).update(global_cap=2)
        self.client = APIClient()

    def test_unproven_requests_share_one_cap_and_never_touch_p0(self):
        unproven = [self.client.post("/p0/", REMOTE_ADDR=f"10.1.0.{i}").status_code for i in range(4)]
        proven = [self.client.post("/p0/", HTTP_X_PROOF="ok").status_code for _ in range(3)]
        self.assertEqual(unproven, [200, 200, 429, 429])
        self.assertEqual(proven, [200, 200, 200])

    def test_a_signed_in_member_is_promoted(self):
        member = Member.objects.create_user(email="promo@example.com", password="pw-123456!", is_active=True)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(member).access_token}")
        statuses = [self.client.post("/p0/").status_code for _ in range(4)]
        self.assertEqual(statuses, [200] * 4)

    def test_unproven_requests_are_shed_like_background_traffic(self):
        from apps.core.services.request_limits.runtime import signals

        with patch.object(signals, "admit", side_effect=lambda tier, now: tier == "p0") as admit:
            self.assertEqual(self.client.post("/p0/").status_code, 429)
            self.assertEqual(self.client.post("/p0/", HTTP_X_PROOF="ok").status_code, 200)
        self.assertEqual([call.args[0] for call in admit.call_args_list], ["p2", "p0"])
