"""The stateful parts: counter store modes, fixed windows and fail-open; process heartbeats; the policy cache;
signal windows; abuse escalation; and the Smart state writes."""

from unittest.mock import patch

from django.core.cache import cache, caches
from django.db import DatabaseError
from django.test import TestCase, override_settings

from apps.core.models import RequestLimitProcess
from apps.core.services.request_limits import counter_mode
from apps.core.services.request_limits.runtime import heartbeat, store
from apps.core.services.request_limits.runtime.context import as_datetime

from ..helpers import START, isolate, limits_with

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


# The policy view is not refreshed on its own here, so each test decides what this process has seen; every tier feeds
# the site-wide signals, so a P3 window alone can call for a cut.
ALL_TIERS = ("p0", "p1", "p2", "p3")
