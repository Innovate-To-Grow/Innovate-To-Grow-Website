"""What Site Settings → Request Limits shows: each scope's limit now, its Smart factor and why, its recent 429s; the
tiers Smart is shedding, this process's last assessment and slots (the P0-reserved ones in use), the counter mode."""

import copy
from datetime import timedelta

from django.conf import settings
from django.test import override_settings

from apps.core.admin.request_limits.cards import assessment_line, clock, per_period, smart_line
from apps.core.models import RequestLimitProcess, RequestRateLimitState
from apps.core.services.request_limits import overview as overview_module
from apps.core.services.request_limits.runtime import refusals, signals, smart
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


class SummaryTests(RequestLimitsAdminTestCase):
    def summary(self):
        return self.client.get(self.url).context["summary"]

    def test_tiers_being_shed_and_recovering(self):
        set_state("ai", 0.5, SHED)
        set_state("telemetry", 0.7, {**SHED, "action": "restore", "tier": "p2"})

        summary = self.summary()

        self.assertEqual(
            summary["tier_lines"],
            [
                "P0 critical: protected (never tightened for load, only by its abuse limits)",
                "P1 interactive: full baseline",
                "P2 background: recovering (1 of 5 scopes below baseline, lowest ×0.70)",
                "P3 heavy: Smart is shedding it (1 of 4 scopes below baseline, lowest ×0.50)",
            ],
        )
        self.assertEqual(summary["shedding"], ["p3"])
        response = self.client.get(self.url)
        self.assertContains(response, 'data-tier-state="p3">P3 heavy: Smart is shedding it')

    def test_the_latest_decision_of_a_tier_wins(self):
        later = (CUT_AT + timedelta(seconds=60)).isoformat()
        set_state("ai", 0.5, SHED)
        set_state("staff-bulk", 0.6, {**SHED, "action": "restore", "at": later})
        self.assertEqual(self.summary()["tier_lines"][3][:21], "P3 heavy: recovering ")

    @override_settings(REQUEST_RATE_LIMITS_ENABLED=False)
    def test_slots_kept_for_p0_in_use(self):
        signals.INFLIGHT.count = 19
        summary = self.summary()

        # The page's own request is not counted: this process tracks slots only while the limiter is on.
        self.assertEqual(
            summary["slots_line"],
            "Request slots in this process: 19 of 20 in use. P1 may fill 18, P2 14, P3 10; 2 are kept for P0 "
            "(1 in use).",
        )
        self.assertEqual(summary["slots"]["p0_reserved_in_use"], 1)
        signals.INFLIGHT.count = 3
        self.assertEqual(self.summary()["slots"]["p0_reserved_in_use"], 0)

    def test_the_last_assessment_of_this_process(self):
        self.assertEqual(
            self.summary()["assessment_line"], "Smart limit has not assessed a signal window in this process yet."
        )
        smart.LAST.update(SHED)
        self.assertEqual(
            self.summary()["assessment_line"],
            "Last assessment in this process (07:55:00 UTC): overload: p95 response time 1800 ms; 80% of request "
            "slots in use → shed P3.",
        )
        self.assertEqual(
            assessment_line({"pressure": "steady", "action": "hold", "tier": "p1", "reasons": [], "at": ""}),
            "Last assessment in this process (): steady → hold.",
        )

    @override_settings(REQUEST_RATE_LIMITS_ENABLED=False)
    def test_limiter_off_banner(self):
        self.assertContains(self.client.get(self.url), "data-limits-off")
        with override_settings(REQUEST_RATE_LIMITS_ENABLED=True):
            response = self.client.get(self.url)
        self.assertNotContains(response, "data-limits-off")
        self.assertTrue(response.context["summary"]["enabled"])

    @override_settings(REQUEST_RATE_LIMITS_ENABLED=False)
    def test_the_page_does_not_register_a_heartbeat_while_the_limiter_is_off(self):
        self.client.get(self.url)
        self.assertFalse(RequestLimitProcess.objects.exists())


class CounterModeTests(RequestLimitsAdminTestCase):
    @override_settings(REQUEST_RATE_LIMITS_ENABLED=True)
    def test_per_process_counters_show_the_live_processes_and_each_share(self):
        for number in range(2):
            RequestLimitProcess.objects.create(
                instance=f"other{number}", pid=100 + number, started_at=as_datetime(START), last_seen=as_datetime(START)
            )
        with store_mode("local"):
            response = self.client.get(self.url)

        summary = response.context["summary"]
        self.assertEqual((summary["counter_mode"], summary["processes"]), ("local", 3))
        self.assertIn("Live processes now (heartbeat rows): 3.", summary["counter_line"])
        lines = self.card(response, "public-read").lines
        self.assertEqual(lines[1], "Per process: 1,000 / minute per caller (3 processes)")
        # A per-view limit keeps its own counter and is not divided.
        self.assertEqual(
            self.card(response, "view-cli-read").lines[0], "Now: 120 / minute (counted per the view's own key)"
        )

    @override_settings(REQUEST_RATE_LIMITS_ENABLED=True)
    def test_shared_counters_hold_site_wide(self):
        RequestLimitProcess.objects.create(
            instance="other", pid=100, started_at=as_datetime(START), last_seen=as_datetime(START)
        )
        with store_mode("shared"):
            summary = self.client.get(self.url).context["summary"]
        self.assertEqual((summary["counter_mode"], summary["processes"]), ("shared", 1))
        self.assertTrue(summary["counter_line"].startswith("Shared counters (Redis)"))


class StatusJsonTests(RequestLimitsAdminTestCase):
    def test_the_status_lists_every_scope_with_its_lines_and_the_summary(self):
        set_state("ai", 0.5, SHED)
        refusals.count("ai", self.clock(), by_limiter=True)

        response = self.client.get(self.status_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertIn("no-cache", response["Cache-Control"])
        data = response.json()
        self.assertEqual(len(data["scopes"]), 51)
        ai = next(item for item in data["scopes"] if item["scope"] == "ai")
        self.assertEqual(
            {key: ai[key] for key in ("tier", "mode", "factor", "per_identity", "global_cap", "period_seconds")},
            {
                "tier": "p3",
                "mode": "smart",
                "factor": 0.5,
                "per_identity": 150,
                "global_cap": 300,
                "period_seconds": 60,
            },
        )
        self.assertEqual(ai["refused"], {"limiter": 1, "view": 0})
        self.assertEqual(ai["lines"][0], "Now: 150 / minute per caller · everyone together 300 / minute · Smart ×0.50")
        view = next(item for item in data["scopes"] if item["scope"] == "view-ai-search")
        self.assertEqual((view["refused"], view["per_process"], view["per_identity"]), (None, None, 5))
        self.assertEqual(data["summary"]["shedding"], ["p3"])
        self.assertEqual(
            set(data["summary"]),
            {
                "enabled",
                "counter_mode",
                "processes",
                "counter_line",
                "tier_lines",
                "tier_states",
                "shedding",
                "assessment_line",
                "slots_line",
                "slots",
            },
        )

    def test_a_deleted_policy_heals_itself(self):
        self.policy("ai").delete()
        self.assertEqual(self.client.get(self.status_url).status_code, 200)
        self.assertTrue(overview_module.RequestRateLimitPolicy.objects.filter(scope="ai").exists())

    def test_the_page_explains_the_tiers(self):
        response = self.client.get(self.url)
        self.assertContains(response, "verification codes they requested (email and SMS)")
        self.assertContains(response, "Smart limit never tightens P0 for load and keeps request slots for it")
        self.assertContains(response, "A code request with neither a sign-in nor a valid anti-abuse proof is not P0.")
        for label in ("P0 critical", "P1 interactive", "P2 background", "P3 heavy"):
            self.assertContains(
                response,
                f'-heading" class="mb-1 text-base font-semibold text-font-important-light dark:text-font-important-dark">{label}</h2>',
            )
        self.assertContains(response, 'data-status-url="/admin/core/request-limits/status/"')
        self.assertContains(response, 'data-refresh-ms="15000"')
        self.assertContains(response, "admin/js/poll-backoff.js")


class SmartLineTests(RequestLimitsAdminTestCase):
    def test_a_cut_without_reasons_names_the_pressure(self):
        view = overview_module.overview()["scopes"]["ai"]
        decision = {"action": "shed", "pressure": "overload", "reasons": [], "at": CUT_AT.isoformat()}
        changed = overview_module.ScopeView(**{**view.__dict__, "factor": 0.5, "decision": decision})
        self.assertEqual(smart_line(changed), "Smart ×0.50 of the baseline: cut at 07:55:00 UTC because of overload.")
