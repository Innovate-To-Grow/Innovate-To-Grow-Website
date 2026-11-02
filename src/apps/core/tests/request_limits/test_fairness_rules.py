"""The pure rules behind the review fixes: per-source flood ceilings and strike limits, the site-wide pace of Smart
changes, which scopes feed the site-wide signals, period-consistent baselines, their validation and the on/off
defaults per settings module."""

import copy
import inspect
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase, override_settings

from apps.core.models import RequestRateLimitPolicy, RequestRateLimitState
from apps.core.services.request_limits.rules.controller import (
    HEALTHY,
    OVERLOAD,
    Pressure,
    ScopeSignal,
    Snapshot,
    plan,
)
from apps.core.services.request_limits.rules.limits import ScopeConfig, effective_limits, strike_limits
from apps.core.services.request_limits.runtime import registry, signals, smart
from apps.core.services.request_limits.runtime.context import as_datetime
from config.settings.base.integrations import request_limits as limits_settings
from config.settings.base.integrations.request_limits.validation import validate_request_limits

from .helpers import START, isolate, limits_with

TIERS = settings.REQUEST_RATE_LIMITS["tiers"]


def config(scope="s", tier="p1", **values):
    fields = {
        "scope": scope,
        "label": scope,
        "tier": tier,
        "identity": "member",
        "baseline": 100,
        "manual": 40,
        "period": 60,
        "smart": True,
        "floor": 0.5,
        "fixed": False,
        "enabled": True,
        "ceiling": None,
        "global_cap": 1_000,
        "source_cap": 200,
        **values,
    }
    return ScopeConfig(**fields)


class SourceCapTests(SimpleTestCase):
    def test_smart_scales_the_source_cap_like_the_aggregate_cap(self):
        self.assertEqual(effective_limits(config(factor=0.5)).source_cap, 100)
        self.assertEqual(effective_limits(config(tier="p0", factor=0.5)).source_cap, 200)

    def test_manual_mode_and_per_process_division(self):
        self.assertEqual(effective_limits(config(smart=False)).source_cap, 200)
        self.assertEqual(effective_limits(config(), processes=3).source_cap, 67)
        self.assertIsNone(effective_limits(config(source_cap=None)).source_cap)

    def test_strike_limits_are_the_full_size_limits(self):
        cut = config(factor=0.5)
        self.assertEqual((effective_limits(cut).per_identity, strike_limits(cut).per_identity), (50, 100))
        self.assertEqual(strike_limits(cut, processes=2).source_cap, 100)


def snapshot(**values):
    return Snapshot(**{"started": 0.0, "ended": 15.0, **values})


class PaceTests(SimpleTestCase):
    """M3: one factor step per scope per ``min_change_seconds`` site-wide, however many processes assess."""

    def test_a_recently_changed_tier_holds_instead_of_cutting_again_or_moving_on(self):
        configs = [config("a", "p3", floor=0.1, factor=0.5, factor_changed_at=100.0), config("b", "p2", floor=0.25)]
        active = snapshot(scopes={"a": ScopeSignal(requests=5), "b": ScopeSignal(requests=5)})
        result = plan(Pressure(OVERLOAD), configs, active, TIERS, now=105.0, hold_seconds=30, change_seconds=15)
        self.assertEqual((result.action, result.tier, result.factors), ("hold", "p3", {}))
        result = plan(Pressure(OVERLOAD), configs, active, TIERS, now=115.0, hold_seconds=30, change_seconds=15)
        self.assertEqual((result.action, result.factors), ("shed", {"a": 0.25}))

    def test_a_recently_changed_scope_is_not_restored_yet(self):
        configs = [config("a", factor=0.5, last_cut_at=0.0, factor_changed_at=100.0)]
        result = plan(Pressure(HEALTHY), configs, snapshot(), TIERS, now=110.0, hold_seconds=30, change_seconds=15)
        self.assertEqual((result.action, result.factors), ("hold", {}))
        result = plan(Pressure(HEALTHY), configs, snapshot(), TIERS, now=115.0, hold_seconds=30, change_seconds=15)
        self.assertEqual(result.factors, {"a": 0.65})


@override_settings(REQUEST_RATE_LIMITS=limits_with(controller={"state_refresh_seconds": 3_600}))
class SiteSignalTests(TestCase):
    """M2: slow-by-nature P3 scopes and the archive proxy do not make the site look overloaded."""

    def setUp(self):
        isolate(self)
        registry.configs(START)
        signals.WINDOW.started = START

    def test_slow_p3_requests_do_not_trip_the_latency_signal(self):
        for _ in range(94):
            signals.record("t-p1", 200, 20.0, START)
        for _ in range(6):
            signals.record("t-p3", 200, 4_000.0, START)  # AI calls
        result = smart.evaluate(START + 15)
        self.assertEqual(smart.LAST["pressure"], "healthy")
        self.assertEqual(result.action, "hold")
        self.assertEqual(RequestRateLimitState.objects.get(scope="t-p3").factor, 1.0)

    def test_the_excluded_scopes_feed_no_site_signal_but_keep_their_own(self):
        for _ in range(30):
            signals.record("legacy-proxy", 502, 10.0, START)
        for _ in range(30):
            signals.record("t-p1", 200, 10.0, START)
        site = smart._site_signal(registry.configs(START), settings.REQUEST_RATE_LIMITS["controller"])
        window = signals.take_if_due(START + 15, site)
        self.assertEqual((window.requests, window.errors), (30, 0))
        self.assertEqual(window.scopes["legacy-proxy"].errors, 30)
        self.assertTrue(site("unknown-scope"))
        self.assertFalse(site("t-p3"))

    def test_another_processs_recent_change_is_not_overwritten(self):
        RequestRateLimitState.objects.filter(scope="t-p2").update(factor_changed_at=as_datetime(START + 10))
        for _ in range(30):
            signals.record("t-p2", 500, 10.0, START)
        result = smart.evaluate(START + 15)  # this process's view still says "never changed"
        self.assertEqual(result.action, "shed")
        self.assertEqual(RequestRateLimitState.objects.get(scope="t-p2").factor, 1.0)


class PeriodTests(TestCase):
    """Minor 4: a deployment count is a rate per its period; a row with another period gets the same rate."""

    def test_a_changed_seed_period_keeps_the_rate(self):
        spec = {**settings.REQUEST_RATE_LIMITS["scopes"]["view-csp-report"], "requests": 600, "period_seconds": 600}
        policy = RequestRateLimitPolicy(
            scope="view-csp-report", **RequestRateLimitPolicy.seed_values("view-csp-report")
        )
        policy.period_seconds = 60
        built = registry.build("view-csp-report", spec, policy)
        self.assertEqual((built.baseline, built.period), (60, 60))

    def test_ceilings_and_caps_follow_the_rate_too(self):
        spec = {**settings.REQUEST_RATE_LIMITS["scopes"]["auth-sign-in"], "period_seconds": 120}
        policy = RequestRateLimitPolicy(scope="auth-sign-in", **RequestRateLimitPolicy.seed_values("auth-sign-in"))
        policy.period_seconds, policy.global_cap = 60, None
        built = registry.build("auth-sign-in", spec, policy)
        self.assertEqual((built.baseline, built.global_cap, built.source_cap), (10, 600, 120))


def broken(mutate):
    config_copy = copy.deepcopy(settings.REQUEST_RATE_LIMITS)
    mutate(config_copy)
    return config_copy


INVALID = {
    "source cap": (lambda c: c["scopes"]["cli"].update(source_cap=0), "scopes.cli.source_cap must be a whole number"),
    "view source cap": (
        lambda c: c["scopes"]["view-csp-report"].update(source_cap=5),
        "scopes.view-csp-report.source_cap must be null",
    ),
    "global without cap": (
        lambda c: c["scopes"]["auth-token-refresh"].update(global_cap=None),
        "scopes.auth-token-refresh.global_cap must be set for identity",
    ),
    "signal tiers": (lambda c: c["controller"].update(signal_tiers=("p9",)), "controller.signal_tiers must be"),
    "no signal tiers": (lambda c: c["controller"].update(signal_tiers=()), "controller.signal_tiers must be"),
    "excluded scopes": (
        lambda c: c["controller"].update(signal_excluded_scopes=("nope",)),
        "controller.signal_excluded_scopes must be",
    ),
    "change pace": (lambda c: c["controller"].update(min_change_seconds=-2), "controller.min_change_seconds must be"),
    "promotions": (lambda c: c["abuse"].update(proof_promotions=0), "abuse.proof_promotions must be a whole number"),
    "proof memory": (lambda c: c["abuse"].update(proof_memory_seconds=0), "abuse.proof_memory_seconds must be"),
}


class ValidationTests(SimpleTestCase):
    def test_the_new_keys_are_validated(self):
        for name, (mutate, message) in INVALID.items():
            with self.subTest(name), self.assertRaisesMessage(ImproperlyConfigured, message):
                validate_request_limits(broken(mutate))

    def test_a_scope_without_a_source_cap_is_valid(self):
        validate_request_limits(broken(lambda c: c["scopes"]["cli"].pop("source_cap")))


SETTINGS = Path(limits_settings.__file__).resolve().parents[3]


class DefaultSwitchTests(SimpleTestCase):
    """Minor 5: on by default (base, production, the local dev server); off for test runs unless the env asks."""

    def test_base_is_on_unless_the_environment_says_otherwise(self):
        self.assertIn("REQUEST_RATE_LIMITS_ENABLED = enabled_from_env(True)", inspect.getsource(limits_settings))

    def test_production_keeps_the_base_default(self):
        source = (SETTINGS / "environments" / "production.py").read_text()
        self.assertNotIn("REQUEST_RATE_LIMITS_ENABLED", source)

    def test_local_test_runs_follow_the_environment(self):
        source = (SETTINGS / "environments" / "local.py").read_text()
        self.assertIn("REQUEST_RATE_LIMITS_ENABLED = enabled_from_env(False)", source)
        self.assertNotIn("REQUEST_RATE_LIMITS_ENABLED = False", source)
