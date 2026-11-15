from dataclasses import replace

from django.test import SimpleTestCase

from apps.core.services.request_limits.rules.controller import (
    STEADY,
    Pressure,
    ScopeSignal,
)
from apps.core.tests.request_limits.rules.test_rules import CALM, OVER, TIERED, applied, config, run, snapshot


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
