"""The stateful parts: counter store modes, fixed windows and fail-open; process heartbeats; the policy cache;
signal windows; abuse escalation; and the Smart state writes."""

from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache, caches
from django.db import DatabaseError
from django.test import TestCase, override_settings

from apps.core.models import RequestLimitProcess, RequestRateLimitPolicy, RequestRateLimitState
from apps.core.services.request_limits import counter_mode, runtime_status
from apps.core.services.request_limits.runtime import abuse, heartbeat, registry, signals, smart, store
from apps.core.services.request_limits.runtime.context import as_datetime, as_seconds

from .helpers import START, isolate, limits_with

LOCMEM = {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "rl-shared-test"}


class StoreTests(TestCase):
    def setUp(self):
        cache.clear()
        self.clock = isolate(self)

    def test_mode_auto_follows_the_default_cache_backend(self):
        self.assertEqual(counter_mode(), store.LOCAL)
        redis = {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": "redis://localhost:1"}
        with override_settings(CACHES={"default": redis, "throttle": LOCMEM}):
            self.assertEqual(store.mode(), store.SHARED)

    def test_mode_can_be_forced(self):
        with override_settings(REQUEST_RATE_LIMITS=limits_with(store={"mode": "shared"})):
            self.assertEqual(store.mode(), store.SHARED)
            self.assertIs(store._cache(), caches["default"])
        with override_settings(REQUEST_RATE_LIMITS=limits_with(store={"mode": "local"})):
            self.assertIs(store._cache(), caches["throttle"])

    def test_fixed_windows_count_and_reset(self):
        self.assertEqual([store.hit("b", 60, START + offset) for offset in (0, 1, 59)], [1, 2, 3])
        self.assertEqual(store.hit("b", 60, START + 60), 1)
        self.assertEqual(store.hit("other", 60, START + 60), 1)
        self.assertEqual(store.window_reset(60, START + 15), 45)
        self.assertEqual(store.window_reset(60, START + 59.9), 1)

    def test_keys_hide_their_parts(self):
        name = store.key("hit", "auth|ip:10.1.2.3")
        self.assertTrue(name.startswith("rl:"))
        self.assertNotIn("10.1.2.3", name)

    def test_a_vanished_entry_is_opened_again(self):
        with patch.object(caches["throttle"], "incr", side_effect=ValueError):
            self.assertEqual(store.hit("b", 60, START), 1)
        self.assertEqual(caches["throttle"].get(store.window_key("b", 60, START)), 1)

    def test_cache_errors_fail_open(self):
        throttle = caches["throttle"]
        with (
            patch.object(throttle, "add", side_effect=OSError),
            patch.object(throttle, "get", side_effect=OSError),
            patch.object(throttle, "set", side_effect=OSError),
            patch.object(throttle, "delete", side_effect=OSError),
            self.assertLogs("apps.core.services.request_limits.runtime.store", "WARNING") as logs,
        ):
            self.assertEqual(store.hit("b", 60, START), 0)
            self.assertIsNone(store.get("x"))
            store.put("x", 1, 5)
            store.delete("x")
        self.assertEqual(len(logs.records), 4)


class HeartbeatTests(TestCase):
    def setUp(self):
        cache.clear()
        isolate(self)

    def test_the_first_call_registers_this_process(self):
        self.assertEqual(heartbeat.live_processes(START), 1)
        row = RequestLimitProcess.objects.get(instance=heartbeat.PROCESS.instance)
        self.assertEqual(
            (row.pid, row.last_seen, row.started_at), (heartbeat.PROCESS.pid, as_datetime(START), as_datetime(START))
        )

    def test_live_rows_are_counted_at_most_every_interval_and_stale_ones_are_not(self):
        heartbeat.live_processes(START)
        for index, age in enumerate((10, 80, 100)):
            RequestLimitProcess.objects.create(
                instance=f"other{index}",
                pid=index + 1,
                started_at=as_datetime(START),
                last_seen=as_datetime(START - age),
            )
        self.assertEqual(heartbeat.live_processes(START + 10), 1)  # not due yet: no query
        with self.assertNumQueries(0):
            heartbeat.live_processes(START + 29)
        self.assertEqual(heartbeat.live_processes(START + 30), 2)
        self.assertEqual(
            RequestLimitProcess.objects.get(instance=heartbeat.PROCESS.instance).last_seen, as_datetime(START + 30)
        )

    def test_rows_dead_for_a_day_are_pruned(self):
        RequestLimitProcess.objects.create(
            instance="dead", pid=9, started_at=as_datetime(START), last_seen=as_datetime(START - 90_000)
        )
        heartbeat.live_processes(START)
        self.assertFalse(RequestLimitProcess.objects.filter(instance="dead").exists())

    def test_a_database_error_keeps_the_last_count(self):
        heartbeat.PROCESS.count = 3
        with (
            patch.object(heartbeat, "_refresh", side_effect=DatabaseError),
            self.assertLogs("apps.core.services.request_limits.runtime.heartbeat", "WARNING"),
        ):
            self.assertEqual(heartbeat.live_processes(START), 3)

    def test_a_forked_child_registers_itself(self):
        heartbeat.live_processes(START)
        parent = heartbeat.PROCESS.instance
        with patch.object(heartbeat.os, "getpid", return_value=heartbeat.PROCESS.pid + 1):
            heartbeat.live_processes(START + 1)
        self.assertNotEqual(heartbeat.PROCESS.instance, parent)
        self.assertEqual(RequestLimitProcess.objects.count(), 2)

    def test_a_busy_lock_skips_the_refresh(self):
        heartbeat.PROCESS.lock.acquire()
        try:
            self.assertEqual(heartbeat.live_processes(START), 1)
        finally:
            heartbeat.PROCESS.lock.release()
        self.assertFalse(RequestLimitProcess.objects.exists())


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
            now += 1
        self.assertEqual(blocks, [30, 60, 120, 240, 480, 900, 900])
        self.assertIsNone(abuse.blocked_for("t-p1", "u:m", now))
        self.assertIsNone(abuse.blocked_for("t-p0", "u:other", now))
        self.assertIsNone(abuse.blocked_for("t-p0", "u:m", now + 900))

    def test_everyone_together_is_never_blocked(self):
        for _ in range(20):
            self.assertIsNone(abuse.strike("t-p0", None, START))
        self.assertIsNone(abuse.blocked_for("t-p0", None, START))


# The policy view is not refreshed on its own here, so each test decides what this process has seen.
@override_settings(REQUEST_RATE_LIMITS=limits_with(controller={"state_refresh_seconds": 3_600}))
class SignalsAndSmartTests(TestCase):
    def setUp(self):
        cache.clear()
        isolate(self)

    def test_windows_close_once_and_report_their_signals(self):
        signals.record("t-p1", 200, 10.0, START)
        signals.record("t-p1", 500, 30.0, START + 1)
        signals.record("t-p1", 429, 1.0, START + 1, served=False)
        self.assertTrue(signals.admit("p1", START + 2))
        signals.release()
        signals.release()  # never below zero
        self.assertIsNone(signals.take_if_due(START + 14))
        window = signals.take_if_due(START + 15)
        self.assertEqual((window.requests, window.errors, window.p95_ms), (2, 1, 30.0))
        self.assertEqual(window.scopes["t-p1"].limited, 1)
        self.assertAlmostEqual(window.inflight_share, 0.05)
        self.assertIsNone(signals.take_if_due(START + 16))
        self.assertEqual(signals.in_flight(), 0)

    def test_latency_reservoir_is_bounded(self):
        with override_settings(
            REQUEST_RATE_LIMITS=limits_with(controller={"max_latency_samples": 5, "state_refresh_seconds": 3_600})
        ):
            for value in range(50):
                signals.record("t-p1", 200, float(value), START)
            self.assertEqual(len(signals.WINDOW.scopes["t-p1"].samples), 5)
        self.assertIsNone(signals.percentile([]))
        self.assertEqual(signals.percentile([1.0, 2.0, 3.0, 4.0]), 4.0)

    def test_an_empty_window_is_not_due(self):
        self.assertIsNone(signals.take_if_due(START + 100))

    def test_evaluate_writes_only_changed_scopes_and_keeps_the_decision(self):
        registry.configs(START)
        signals.WINDOW.started = START
        for _ in range(30):
            signals.record("t-p3", 500, 10.0, START)
        result = smart.evaluate(START + 15)
        self.assertEqual((result.action, result.tier), ("shed", "p3"))
        state = RequestRateLimitState.objects.get(scope="t-p3")
        self.assertEqual((state.factor, state.last_cut_at), (0.5, as_datetime(START + 15)))
        self.assertEqual(state.last_decision["reasons"], ["100.0% server errors"])
        self.assertEqual(RequestRateLimitState.objects.get(scope="t-p2").factor, 1.0)
        self.assertEqual(registry.configs(START + 16)["t-p3"].factor, 0.5)
        self.assertEqual(smart.LAST["action"], "shed")
        self.assertIsNone(smart.evaluate(START + 16))

    def test_a_row_changed_by_another_process_is_not_overwritten(self):
        registry.configs(START)
        RequestRateLimitState.objects.filter(scope="t-p3").update(factor=0.8)  # another process cut it first
        signals.WINDOW.started = START
        for _ in range(30):
            signals.record("t-p3", 500, 10.0, START)
        smart.evaluate(START + 15)
        self.assertEqual(RequestRateLimitState.objects.get(scope="t-p3").factor, 0.8)
        self.assertEqual(registry.configs(START + 16)["t-p3"].factor, 0.8)

    def test_a_failed_write_is_logged(self):
        registry.configs(START)
        signals.WINDOW.started = START
        for _ in range(30):
            signals.record("t-p3", 500, 10.0, START)
        with (
            patch.object(smart.RequestRateLimitState.objects, "filter", side_effect=DatabaseError),
            self.assertLogs("apps.core.services.request_limits.runtime.smart", "WARNING"),
        ):
            smart.evaluate(START + 15)
        self.assertEqual(registry.configs(START + 16)["t-p3"].factor, 1.0)

    def test_restore_does_not_move_the_last_cut(self):
        registry.configs(START)
        cut_at = as_datetime(START - 100)
        RequestRateLimitState.objects.filter(scope="t-p1").update(factor=0.5, last_cut_at=cut_at)
        registry.invalidate()
        registry.configs(START)
        signals.WINDOW.started = START
        smart.evaluate(START + 15)
        state = RequestRateLimitState.objects.get(scope="t-p1")
        self.assertEqual((round(state.factor, 2), state.last_cut_at), (0.65, cut_at))
        self.assertEqual(state.factor_changed_at, as_datetime(START + 15))

    def test_runtime_status(self):
        status = runtime_status()
        self.assertEqual(status["counter_mode"], "local")
        self.assertEqual(status["processes"], 1)
        self.assertEqual(status["slots"], {"p0": 20, "p1": 18, "p2": 14, "p3": 10})
        row = next(item for item in status["scopes"] if item["scope"] == "t-p0")
        self.assertEqual((row["per_identity"], row["global_cap"], row["mode"], row["factor"]), (5, 1_000, "smart", 1.0))
        RequestLimitProcess.objects.create(
            instance="other", pid=2, started_at=as_datetime(START), last_seen=as_datetime(START)
        )
        heartbeat.PROCESS.refreshed_at = START - timedelta(minutes=1).total_seconds()
        row = next(item for item in runtime_status()["scopes"] if item["scope"] == "t-p0")
        self.assertEqual(row["per_process"], 3)
