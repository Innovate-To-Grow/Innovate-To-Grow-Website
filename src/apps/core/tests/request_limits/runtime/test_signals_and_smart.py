from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.db import DatabaseError
from django.test import TestCase, override_settings

from apps.core.models import RequestLimitProcess, RequestRateLimitState
from apps.core.services.request_limits import runtime_status
from apps.core.services.request_limits.runtime import heartbeat, registry, signals, smart
from apps.core.services.request_limits.runtime.context import as_datetime
from apps.core.tests.request_limits.runtime.test_runtime import ALL_TIERS

from ..helpers import START, isolate, limits_with


@override_settings(
    REQUEST_RATE_LIMITS=limits_with(controller={"state_refresh_seconds": 3_600, "signal_tiers": ALL_TIERS})
)
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
            REQUEST_RATE_LIMITS=limits_with(
                controller={"max_latency_samples": 5, "state_refresh_seconds": 3_600, "signal_tiers": ALL_TIERS}
            )
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
