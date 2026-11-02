"""The pure rules: Smart-over-manual precedence, per-process division, tier slots and the priority-ordered AIMD
controller (shed P3 → P2 → P1, never P0; restore P1 → P2 → P3)."""

from dataclasses import replace

from django.conf import settings
from django.test import SimpleTestCase

from apps.core.services.request_limits.rules.controller import (
    HEALTHY,
    OVERLOAD,
    STEADY,
    Pressure,
    ScopeSignal,
    Snapshot,
    assess,
    plan,
)
from apps.core.services.request_limits.rules.limits import (
    ScopeConfig,
    admission_limit,
    effective_limits,
    smart_factor,
)

TIERS = settings.REQUEST_RATE_LIMITS["tiers"]
CONTROLLER = settings.REQUEST_RATE_LIMITS["controller"]


def config(scope="s", tier="p1", **values):
    fields = {
        "scope": scope,
        "label": scope,
        "tier": tier,
        "identity": "ip",
        "baseline": 100,
        "manual": 40,
        "period": 60,
        "smart": True,
        "floor": 0.5,
        "fixed": False,
        "enabled": True,
        "ceiling": None,
        "global_cap": 1_000,
        **values,
    }
    return ScopeConfig(**fields)


def snapshot(**values):
    fields = {"started": 0.0, "ended": 15.0, **values}
    return Snapshot(**fields)


class EffectiveLimitsTests(SimpleTestCase):
    def test_smart_uses_the_baseline_times_the_factor_and_never_reads_the_manual_limit(self):
        limits = effective_limits(config(factor=0.7, manual=3))
        self.assertEqual((limits.mode, limits.per_identity, limits.global_cap, limits.factor), ("smart", 70, 700, 0.7))
        self.assertEqual(limits.period, 60)

    def test_smart_never_goes_below_the_floor_nor_above_full(self):
        self.assertEqual(effective_limits(config(factor=0.1)).per_identity, 50)
        self.assertEqual(effective_limits(config(factor=3.0)).per_identity, 100)
        self.assertEqual(smart_factor(config(factor=0.2, floor=1.5)), 1.0)

    def test_p0_and_fixed_scopes_are_never_tightened(self):
        for values in ({"tier": "p0"}, {"fixed": True}):
            with self.subTest(**values):
                self.assertEqual(effective_limits(config(factor=0.25, **values)).per_identity, 100)

    def test_manual_mode_uses_the_manual_limit_and_the_cap_unscaled(self):
        limits = effective_limits(config(smart=False, factor=0.25))
        self.assertEqual(
            (limits.mode, limits.per_identity, limits.global_cap, limits.factor), ("manual", 40, 1_000, None)
        )

    def test_the_per_caller_ceiling_caps_both_modes(self):
        self.assertEqual(effective_limits(config(ceiling=30)).per_identity, 30)
        self.assertEqual(effective_limits(config(smart=False, ceiling=30)).per_identity, 30)

    def test_limits_never_reach_zero(self):
        limits = effective_limits(config(baseline=1, global_cap=1, factor=0.5, floor=0.1))
        self.assertEqual((limits.per_identity, limits.global_cap), (1, 1))

    def test_no_aggregate_cap(self):
        self.assertIsNone(effective_limits(config(global_cap=None)).global_cap)

    def test_per_process_division_rounds_up(self):
        limits = effective_limits(config(global_cap=1_000), processes=3)
        self.assertEqual((limits.per_identity, limits.global_cap), (34, 334))
        self.assertEqual(effective_limits(config(baseline=1), processes=4).per_identity, 1)
        self.assertEqual(effective_limits(config(global_cap=None), processes=4).global_cap, None)

    def test_sheddable(self):
        self.assertTrue(config().sheddable)
        self.assertFalse(config(tier="p0").sheddable)
        self.assertFalse(config(fixed=True).sheddable)
        self.assertFalse(config(smart=False).sheddable)


class AdmissionLimitTests(SimpleTestCase):
    def test_default_shares_of_twenty_slots(self):
        slots = {tier: admission_limit(tier, 20, TIERS, 2) for tier in ("p0", "p1", "p2", "p3")}
        self.assertEqual(slots, {"p0": 20, "p1": 18, "p2": 14, "p3": 10})

    def test_p0_reserve_wins_over_a_large_share(self):
        self.assertEqual(admission_limit("p1", 10, TIERS, 2), 8)
        self.assertEqual(admission_limit("p1", 10, TIERS, 4), 6)

    def test_a_tiny_limit_still_admits_one_of_each_tier(self):
        self.assertEqual(admission_limit("p3", 2, TIERS, 2), 1)


class AssessTests(SimpleTestCase):
    def test_too_few_requests_ignore_latency_and_errors(self):
        pressure = assess(snapshot(requests=5, errors=5, p95_ms=9_999), CONTROLLER)
        self.assertEqual(pressure.level, HEALTHY)
        self.assertIsNone(pressure.values["p95_ms"])

    def test_each_overload_signal(self):
        cases = {
            "slots": (snapshot(inflight_share=0.8), "80% of request slots in use"),
            "refused": (snapshot(refused=3), "3 requests refused for lack of a slot"),
            "errors": (snapshot(requests=100, errors=6), "6.0% server errors"),
            "latency": (snapshot(requests=100, p95_ms=2_000), "p95 response time 2000 ms"),
        }
        for name, (window, reason) in cases.items():
            with self.subTest(name):
                pressure = assess(window, CONTROLLER)
                self.assertEqual(pressure.level, OVERLOAD)
                self.assertEqual(pressure.reasons, (reason,))

    def test_between_the_thresholds_is_steady(self):
        for window in (
            snapshot(inflight_share=0.5),
            snapshot(requests=100, errors=2),
            snapshot(requests=100, p95_ms=1_000),
        ):
            with self.subTest(window=window):
                self.assertEqual(assess(window, CONTROLLER).level, STEADY)

    def test_healthy_reports_its_values(self):
        pressure = assess(snapshot(requests=100, p95_ms=100.04, inflight_share=0.1), CONTROLLER)
        self.assertEqual(pressure.level, HEALTHY)
        self.assertEqual(
            pressure.values,
            {"requests": 100, "error_share": 0.0, "p95_ms": 100.0, "inflight_share": 0.1, "refused": 0},
        )


TIERED = [
    config("a0", "p0", factor=1.0),
    config("a1", "p1", factor=1.0, floor=0.5),
    config("a2", "p2", factor=1.0, floor=0.25),
    config("a3", "p3", factor=1.0, floor=0.1),
    config("fixed3", "p3", factor=1.0, fixed=True),
    config("manual3", "p3", factor=1.0, smart=False),
]
BUSY = snapshot(scopes={scope.scope: ScopeSignal(requests=10) for scope in TIERED}, requests=60, inflight_share=0.9)
OVER = Pressure(OVERLOAD)
CALM = Pressure(HEALTHY)


def run(configs, pressure, window=BUSY, now=1_000.0, hold=30):
    return plan(pressure, configs, window, TIERS, now=now, hold_seconds=hold)


def applied(configs, result, now=1_000.0, cut=False):
    return [
        replace(item, factor=result.factors[item.scope], last_cut_at=now if cut else item.last_cut_at)
        if item.scope in result.factors
        else item
        for item in configs
    ]


class PlanTests(SimpleTestCase):
    def test_overload_sheds_p3_then_p2_then_p1_and_never_p0_or_fixed_or_manual(self):
        configs, order = TIERED, []
        for _round in range(40):
            result = run(configs, OVER)
            if result.action != "shed":
                break
            order.append(result.tier)
            self.assertNotIn("a0", result.factors)
            self.assertNotIn("fixed3", result.factors)
            self.assertNotIn("manual3", result.factors)
            configs = applied(configs, result, cut=True)
        # Each tier is cut down to its floor before the next one is touched.
        tiers_seen = [tier for index, tier in enumerate(order) if index == 0 or order[index - 1] != tier]
        self.assertEqual(tiers_seen, ["p3", "p2", "p1"])
        factors = {item.scope: item.factor for item in configs}
        self.assertEqual(factors["a0"], 1.0)
        self.assertAlmostEqual(factors["a3"], 0.1)
        self.assertAlmostEqual(factors["a2"], 0.25)
        self.assertAlmostEqual(factors["a1"], 0.5)
        self.assertEqual(run(configs, OVER).action, "hold")

    def test_each_tier_uses_its_own_decrease_factor(self):
        result = run(TIERED, OVER)
        self.assertEqual((result.tier, result.factors), ("p3", {"a3": 0.5}))
        only_p2 = [config("a2", "p2")]
        self.assertAlmostEqual(run(only_p2, OVER, snapshot(scopes={"a2": ScopeSignal(1)})).factors["a2"], 0.7)
        only_p1 = [config("a1", "p1")]
        self.assertAlmostEqual(run(only_p1, OVER, snapshot(scopes={"a1": ScopeSignal(1)})).factors["a1"], 0.85)

    def test_an_idle_tier_is_skipped(self):
        window = snapshot(scopes={"a2": ScopeSignal(requests=5)})
        result = run(TIERED, OVER, window)
        self.assertEqual((result.tier, list(result.factors)), ("p2", ["a2"]))

    def test_healthy_restores_p1_then_p2_then_p3(self):
        configs = [replace(item, factor=item.floor, last_cut_at=0.0) if item.sheddable else item for item in TIERED]
        order = []
        for step in range(60):
            result = run(configs, CALM, now=1_000.0 + step)
            if result.action != "restore":
                break
            order.append(result.tier)
            configs = applied(configs, result)
        self.assertEqual(
            [tier for index, tier in enumerate(order) if index == 0 or order[index - 1] != tier], ["p1", "p2", "p3"]
        )
        self.assertTrue(all(item.factor == 1.0 for item in configs))
        self.assertEqual(run(configs, CALM).action, "hold")

    def test_recovery_waits_for_the_hold_and_keeps_the_strict_order(self):
        configs = [config("a1", "p1", factor=0.5, last_cut_at=990.0), config("a3", "p3", factor=0.1, last_cut_at=0.0)]
        held = run(configs, CALM, now=1_000.0, hold=30)
        self.assertEqual((held.action, held.tier, held.factors), ("hold", "p1", {}))
        restored = run(configs, CALM, now=1_020.0, hold=30)
        self.assertEqual((restored.tier, restored.factors), ("p1", {"a1": 0.65}))

    def test_steady_changes_nothing(self):
        self.assertEqual(run(TIERED, Pressure(STEADY)).action, "hold")

    def test_snapshot_active(self):
        window = snapshot(scopes={"a": ScopeSignal(requests=1), "b": ScopeSignal(), "r": ScopeSignal(limited=2)})
        self.assertTrue(window.active("a"))
        self.assertTrue(window.active("r"))
        self.assertFalse(window.active("b"))
        self.assertFalse(window.active("c"))
