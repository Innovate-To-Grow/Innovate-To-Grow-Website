"""What Site Settings → Request Limits shows: each scope's limit now, its Smart factor and why, its recent 429s; the
tiers Smart is shedding, this process's last assessment and slots (the P0-reserved ones in use), the counter mode."""

import copy

from django.conf import settings
from django.test import override_settings

from apps.core.admin.request_limits.cards import clock, per_period
from apps.core.models import RequestRateLimitState
from apps.core.services.request_limits.runtime import refusals
from apps.core.services.request_limits.runtime.context import as_datetime
from apps.core.tests.request_limits.helpers import START

from .helpers import RequestLimitsAdminTestCase

CUT_AT = as_datetime(START - 300)
SHED = {
    "pressure": "overload",
    "action": "shed",
    "tier": "p3",
    "reasons": ["p95 response time 1800 ms", "80% of request slots in use"],
    "signals": {"p95_ms": 1800.0},
    "at": CUT_AT.isoformat(),
}


def set_state(scope, factor, decision):
    RequestRateLimitState.objects.update_or_create(
        scope=scope, defaults={"factor": factor, "factor_changed_at": CUT_AT, "last_decision": decision}
    )


def store_mode(mode):
    config = copy.deepcopy(settings.REQUEST_RATE_LIMITS)
    config["store"]["mode"] = mode
    return override_settings(REQUEST_RATE_LIMITS=config)


class ScopeLineTests(RequestLimitsAdminTestCase):
    def state(self, scope, factor, decision=None):
        RequestRateLimitState.objects.update_or_create(
            scope=scope,
            defaults={
                "factor": factor,
                "factor_changed_at": CUT_AT,
                "last_cut_at": CUT_AT,
                "last_decision": decision or {},
            },
        )

    def lines(self, scope):
        return list(self.card(self.client.get(self.url), scope).lines)

    def test_a_shed_scope_shows_its_lower_limit_and_why(self):
        self.state("ai", 0.5, SHED)

        self.assertEqual(
            self.lines("ai"),
            [
                "Now: 150 / minute per caller · everyone together 300 / minute · Smart ×0.50",
                "Smart ×0.50 of the baseline: cut at 07:55:00 UTC because of p95 response time 1800 ms; 80% of "
                "request slots in use.",
                "429s in the last 15 min: 0 (0 by this limiter, 0 by the view's own limits)",
            ],
        )

    def test_a_per_view_limit_follows_its_parent(self):
        self.state("ai", 0.5, SHED)

        self.assertEqual(
            self.lines("view-ai-search"),
            [
                "Now: 5 / minute (counted per the view's own key)",
                "Smart ×0.50 of the baseline (follows AI search and assistant): cut at 07:55:00 UTC because of p95 "
                "response time 1800 ms; 80% of request slots in use.",
            ],
        )
        html = self.card_html(self.client.get(self.url), "view-ai-search")
        self.assertIn("Per-view limit under AI search and assistant.", html)

    def test_a_restored_scope_says_so(self):
        self.state("public-heavy", 0.6, {**SHED, "action": "restore", "reasons": [], "pressure": "healthy"})
        self.assertEqual(self.lines("public-heavy")[1], "Smart ×0.60 of the baseline: restored at 07:55:00 UTC.")

    def test_an_unchanged_scope_is_at_full_baseline(self):
        self.assertEqual(self.lines("ai")[1], "Smart ×1.00 of the baseline: no Smart change yet.")

    def test_p0_and_fixed_scopes_are_never_tightened(self):
        self.state("auth-code-send", 0.2, SHED)
        self.state("checkin-status", 0.2, SHED)

        self.assertEqual(
            self.lines("auth-code-send")[:2],
            [
                "Now: 10 / minute per caller · everyone together 600 / minute · per anonymous source 120 / minute · Smart ×1.00",
                "P0: Smart limit never tightens it for load; only its abuse limits apply.",
            ],
        )
        self.assertEqual(self.lines("checkin-status")[1], "Fixed: Smart limit never tightens it.")

    def test_smart_off_shows_the_manual_limit_and_ignores_a_stored_factor(self):
        self.state("ai", 0.2, SHED)
        self.set_policy("ai", smart_enabled=False, manual_requests=12)

        self.assertEqual(
            self.lines("ai")[:2],
            [
                "Now: 12 / minute per caller · everyone together 600 / minute · manual limit",
                "Smart limit is off: the manual limit applies.",
            ],
        )

    def test_a_switched_off_scope_is_not_limited(self):
        self.set_policy("ai", enabled=False)
        self.assertEqual(self.lines("ai")[0], "Not limited: this scope is switched off.")

    def test_an_everyone_together_scope_has_no_per_caller_limit(self):
        self.assertEqual(
            self.lines("auth-token-refresh")[0],
            "Now: everyone together 6,000 / minute · per anonymous source 1,200 / minute · Smart ×1.00",
        )

    def test_recent_429s_are_shown_per_route_scope(self):
        refusals.count("ai", self.clock(), by_limiter=True)
        refusals.count("ai", self.clock(), by_limiter=True)
        refusals.count("ai", self.clock(), by_limiter=False)

        self.assertEqual(
            self.lines("ai")[-1], "429s in the last 15 min: 3 (2 by this limiter, 1 by the view's own limits)"
        )

    def test_periods_are_spelled_out(self):
        self.assertEqual(per_period(1_200, 60), "1,200 / minute")
        self.assertEqual(per_period(10, 3_600), "10 / hour")
        self.assertEqual(per_period(10, 86_400), "10 / day")
        self.assertEqual(per_period(3, 1), "3 / second")
        self.assertEqual(per_period(20, 900), "20 / 900 s")
        self.assertEqual(self.lines("view-maintenance-bypass")[0], "Now: 20 / 900 s (counted per the view's own key)")

    def test_a_bad_decision_time_is_left_out(self):
        self.assertEqual(clock("not a time"), "")
        self.assertEqual(clock(None), "")
