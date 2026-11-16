from unittest.mock import patch

from django.core.cache import cache
from django.db import DatabaseError
from django.test import TestCase, override_settings

from apps.core.models import RequestRateLimitPolicy, RequestRateLimitState
from apps.core.services.request_limits.runtime import abuse, registry
from apps.core.services.request_limits.runtime.context import as_datetime, as_seconds

from ..helpers import START, isolate, limits_with


@override_settings(REQUEST_RATE_LIMITS=limits_with())
class RegistryTests(TestCase):
    def setUp(self):
        cache.clear()
        isolate(self)

    def test_loads_every_scope_and_heals_missing_rows(self):
        configs = registry.configs(START)
        self.assertIn("t-p3", configs)
        self.assertTrue(RequestRateLimitPolicy.objects.filter(scope="t-p3").exists())
        self.assertTrue(RequestRateLimitState.objects.filter(scope="t-p3").exists())
        self.assertEqual((configs["t-p3"].floor, configs["t-p3"].factor), (0.1, 1.0))

    def test_reads_the_database_at_most_every_refresh_interval(self):
        registry.configs(START)
        RequestRateLimitPolicy.objects.filter(scope="t-p1").update(manual_requests=3)
        with self.assertNumQueries(0):
            self.assertEqual(registry.configs(START + 9)["t-p1"].manual, 1_000)
        self.assertEqual(registry.configs(START + 10)["t-p1"].manual, 3)

    def test_a_save_invalidates_after_commit(self):
        registry.configs(START)
        policy = RequestRateLimitPolicy.objects.get(scope="t-p1")
        policy.manual_requests = 4
        with self.captureOnCommitCallbacks(execute=True):
            policy.save()
        self.assertEqual(registry.configs(START + 1)["t-p1"].manual, 4)

    def test_smart_off_holds_the_factor_at_full(self):
        registry.configs(START)
        RequestRateLimitState.objects.filter(scope="t-p2").update(factor=0.3, last_cut_at=as_datetime(START))
        RequestRateLimitPolicy.objects.filter(scope="t-p2").update(smart_enabled=False)
        registry.invalidate()
        self.assertEqual(registry.configs(START + 1)["t-p2"].factor, 1.0)
        state = RequestRateLimitState.objects.get(scope="t-p2")
        self.assertEqual((state.factor, state.last_cut_at), (1.0, None))

    def test_database_errors_use_the_seeds_then_keep_the_last_view(self):
        with (
            patch.object(registry, "_rows", side_effect=DatabaseError),
            self.assertLogs("apps.core.services.request_limits.runtime.registry", "WARNING"),
        ):
            seeded = registry.configs(START)
        self.assertEqual(seeded["t-p1"].manual, 1_000)
        registry.configs(START + 20)
        RequestRateLimitState.objects.filter(scope="t-p1").update(factor=0.5)
        registry.invalidate()
        registry.configs(START + 21)
        with patch.object(registry, "_rows", side_effect=DatabaseError), self.assertLogs(level="WARNING"):
            self.assertEqual(registry.configs(START + 40)["t-p1"].factor, 0.5)

    def test_a_settings_change_invalidates(self):
        registry.configs(START)
        with override_settings(REQUEST_RATE_LIMITS=limits_with(scopes={"t-new": limits_with()["scopes"]["t-p1"]})):
            self.assertIn("t-new", registry.configs(START + 1))

    def test_a_lowered_deployment_ceiling_holds_existing_rows(self):
        registry.configs(START)
        RequestRateLimitPolicy.objects.filter(scope="t-p1").update(identity_ceiling=None, global_cap=10_000)
        lowered = limits_with()
        lowered["scopes"]["t-p1"] = {**lowered["scopes"]["t-p1"], "identity_ceiling": 40, "global_cap": 500}
        with override_settings(REQUEST_RATE_LIMITS=lowered):
            config = registry.configs(START + 1)["t-p1"]
        self.assertEqual((config.ceiling, config.global_cap), (40, 500))
        # A row below the deployment's maximum keeps its own value...
        RequestRateLimitPolicy.objects.filter(scope="t-p1").update(identity_ceiling=30, global_cap=200)
        registry.invalidate()
        with override_settings(REQUEST_RATE_LIMITS=lowered):
            config = registry.configs(START + 2)["t-p1"]
        self.assertEqual((config.ceiling, config.global_cap), (30, 200))
        # ...and so does one whose deployment sets no per-caller ceiling at all.
        registry.invalidate()
        config = registry.configs(START + 3)["t-p1"]
        self.assertEqual((config.ceiling, config.global_cap), (30, 200))

    def test_times_round_trip(self):
        self.assertEqual(as_seconds(as_datetime(START)), START)
        self.assertIsNone(as_seconds(None))


@override_settings(REQUEST_RATE_LIMITS=limits_with())
class AbuseTests(TestCase):
    def setUp(self):
        cache.clear()
        isolate(self)

    def test_strikes_block_with_a_growing_bounded_cooldown(self):
        blocks = []
        now = START
        for _round in range(7):
            for _strike in range(9):
                self.assertIsNone(abuse.strike("t-p0", "u:m", now))
            blocks.append(abuse.strike("t-p0", "u:m", now))
            self.assertEqual(abuse.blocked_for("t-p0", "u:m", now), blocks[-1])
            self.assertIsNone(abuse.blocked_for("t-p1", "u:m", now))
            self.assertIsNone(abuse.blocked_for("t-p0", "u:other", now))
            now += blocks[-1]
            self.assertIsNone(abuse.blocked_for("t-p0", "u:m", now))
        self.assertEqual(blocks, [30, 60, 120, 240, 480, 900, 900])

    def test_strikes_during_a_block_never_lengthen_it(self):
        # B1: a caller that keeps sending while blocked (here 1 refusal a second) is unblocked when the block ends.
        for _ in range(10):
            abuse.strike("t-p0", "ip:campus", START)
        self.assertEqual(abuse.blocked_for("t-p0", "ip:campus", START), 30)
        for second in range(1, 30):
            self.assertIsNone(abuse.strike("t-p0", "ip:campus", START + second))
        self.assertEqual(abuse.blocked_for("t-p0", "ip:campus", START + 29), 1)
        self.assertIsNone(abuse.blocked_for("t-p0", "ip:campus", START + 30))

    def test_everyone_together_is_never_blocked(self):
        for _ in range(20):
            self.assertIsNone(abuse.strike("t-p0", None, START))
        self.assertIsNone(abuse.blocked_for("t-p0", None, START))
