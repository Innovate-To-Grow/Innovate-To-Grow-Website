"""Per-view limits read live from the policy table: seeds while the limiter is off, the policy row (Smart over
manual, the parent's Smart factor, disabled) while it is on, the DRF bases, and the failure lockout."""

from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.core.models import RequestRateLimitPolicy, RequestRateLimitState
from apps.core.services.request_limits.runtime import registry
from apps.core.services.request_limits.view_limits import (
    MemberRateThrottle,
    PolicyRateThrottle,
    ViewRate,
    view_rate,
)

from ..helpers import isolate, limits_with

ON = override_settings(REQUEST_RATE_LIMITS_ENABLED=True)


def set_policy(scope, **values):
    policy = RequestRateLimitPolicy.for_scope(scope)
    for name, value in values.items():
        setattr(policy, name, value)
    policy.save()
    registry.invalidate()


def set_factor(scope, factor):
    RequestRateLimitState.objects.update_or_create(scope=scope, defaults={"factor": factor})
    registry.invalidate()


@override_settings(REQUEST_RATE_LIMITS_ENABLED=False)
class SeedTests(TestCase):
    """The request limiter is off in the test settings: the seeds apply and the database is never read."""

    def setUp(self):
        cache.clear()
        isolate(self)

    def test_every_per_view_limit_keeps_todays_rate(self):
        expected = {
            "view-code-send-email": (5, 60),
            "view-code-send-sms": (5, 60),
            "view-code-send-sms-ip": (5, 60),
            "view-code-verify": (60, 60),
            "view-invitation": (10, 3600),
            "view-ses-events": (600, 60),
            "view-contact-email-create": (5, 3600),
            "view-past-project-share": (10, 60),
            "view-past-project-share-update": (120, 60),
            "view-cli-read": (120, 60),
            "view-cli-write": (60, 60),
            "view-pageview-visitor": (120, 60),
            "view-pageview-legacy": (600, 60),
            "view-pageview-total": (3000, 60),
            "view-csp-report": (60, 60),
            "view-ai-search": (10, 60),
            "view-assistant-chat": (6, 60),
            "view-assistant-legacy": (60, 60),
        }
        for scope, (requests, period) in expected.items():
            with self.subTest(scope=scope):
                self.assertEqual(view_rate(scope), ViewRate(requests, period))

    def test_the_new_limits(self):
        self.assertEqual(view_rate("view-contact-phone-create"), ViewRate(5, 3600))
        self.assertEqual(view_rate("view-change-password"), ViewRate(10, 3600))
        self.assertEqual(view_rate("view-registration-create"), ViewRate(20, 3600))
        self.assertEqual(view_rate("view-ticket-email-resend"), ViewRate(10, 3600))
        self.assertEqual(view_rate("view-maintenance-bypass"), ViewRate(20, 900))
        self.assertEqual(view_rate("view-ses-rejected"), ViewRate(60, 60))

    def test_no_query_while_the_limiter_is_off(self):
        with self.assertNumQueries(0):
            view_rate("view-code-verify")

    def test_a_disabled_seed_does_not_limit(self):
        config = limits_with(scopes={})
        config["scopes"]["view-code-verify"] = {**config["scopes"]["view-code-verify"], "enabled": False}
        with override_settings(REQUEST_RATE_LIMITS=config):
            self.assertIsNone(view_rate("view-code-verify"))

    def test_the_seeds_follow_settings_overrides(self):
        config = limits_with(scopes={})
        config["scopes"]["view-code-verify"] = {**config["scopes"]["view-code-verify"], "requests": 3}
        with override_settings(REQUEST_RATE_LIMITS=config):
            self.assertEqual(view_rate("view-code-verify"), ViewRate(3, 60))

    def test_per_view_limits_are_seeded_as_policy_rows(self):
        policy = RequestRateLimitPolicy.objects.get(scope="view-code-verify")
        self.assertEqual((policy.identity, policy.manual_requests, policy.tier), ("view", 60, "p0"))
        self.assertTrue(policy.smart_enabled)


@ON
class LivePolicyTests(TestCase):
    """With the request limiter on, the policy row decides, and an admin edit applies without a restart."""

    def setUp(self):
        cache.clear()
        isolate(self)

    def test_smart_takes_priority_over_the_manual_limit(self):
        set_policy("view-past-project-share", manual_requests=2)
        self.assertEqual(view_rate("view-past-project-share"), ViewRate(10, 60))

    def test_with_smart_off_the_manual_limit_applies(self):
        set_policy("view-past-project-share", smart_enabled=False, manual_requests=2, period_seconds=30)
        self.assertEqual(view_rate("view-past-project-share"), ViewRate(2, 30))

    def test_the_manual_limit_is_capped_by_the_ceiling(self):
        set_policy("view-past-project-share", smart_enabled=False, manual_requests=5, identity_ceiling=5)
        RequestRateLimitPolicy.objects.filter(scope="view-past-project-share").update(identity_ceiling=3)
        registry.invalidate()
        self.assertEqual(view_rate("view-past-project-share"), ViewRate(3, 60))

    def test_a_disabled_policy_does_not_limit(self):
        set_policy("view-ai-search", enabled=False)
        self.assertIsNone(view_rate("view-ai-search"))

    def test_an_admin_edit_applies_after_the_commit_without_a_restart(self):
        self.assertEqual(view_rate("view-cli-write"), ViewRate(60, 60))
        policy = RequestRateLimitPolicy.for_scope("view-cli-write")
        policy.smart_enabled, policy.manual_requests = False, 7
        with self.captureOnCommitCallbacks(execute=True):
            policy.save()
        self.assertEqual(view_rate("view-cli-write"), ViewRate(7, 60))

    def test_smart_lowers_a_sheddable_limit_with_its_parent(self):
        set_factor("ai", 0.5)
        self.assertEqual(view_rate("view-ai-search"), ViewRate(5, 60))
        self.assertEqual(view_rate("view-assistant-chat"), ViewRate(3, 60))

    def test_never_below_the_floor(self):
        set_factor("ai", 0.01)
        floor = settings.REQUEST_RATE_LIMITS["tiers"]["p3"]["floor"]
        self.assertEqual(view_rate("view-ai-search"), ViewRate(max(1, int(10 * floor)), 60))
        set_policy("view-ai-search", smart_floor=Decimal("0.5"))
        self.assertEqual(view_rate("view-ai-search"), ViewRate(5, 60))

    def test_p0_and_fixed_limits_are_never_tightened_for_load(self):
        set_factor("auth-code-send", 0.2)
        set_factor("webhook-ses", 0.2)
        self.assertEqual(view_rate("view-code-send-sms"), ViewRate(5, 60))
        self.assertEqual(view_rate("view-ses-events"), ViewRate(600, 60))
        set_policy("view-pageview-total", fixed=True)
        set_factor("telemetry", 0.5)
        self.assertEqual(view_rate("view-pageview-total"), ViewRate(3000, 60))

    def test_a_parent_with_smart_off_does_not_lower_its_children(self):
        set_policy("ai", smart_enabled=False)
        RequestRateLimitState.objects.filter(scope="ai").update(factor=0.5)
        registry.invalidate()
        self.assertEqual(view_rate("view-ai-search"), ViewRate(10, 60))

    def test_a_scope_the_registry_does_not_know_falls_back_to_its_seed(self):
        with patch.object(registry, "configs", return_value={}):
            self.assertEqual(view_rate("view-ai-search"), ViewRate(10, 60))


class Ai(PolicyRateThrottle):
    scope = "test_ai"
    policy_scope = "view-ai-search"


class Member(MemberRateThrottle):
    scope = "test_member"
    policy_scope = "view-code-verify"
