"""REQUEST_RATE_LIMITS: the seeds, the env overrides deep-merged into them, the validation at import, and the
on/off switch per environment."""

import copy
import importlib
import json
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from config.settings.base.integrations import request_limits as limits_settings
from config.settings.base.integrations.request_limits import enabled_from_env, runtime
from config.settings.base.integrations.request_limits.validation import load_request_limits, validate_request_limits

DEFAULTS = limits_settings.DEFAULTS


def load(overrides):
    return load_request_limits(DEFAULTS, json.dumps(overrides))


def broken(mutate):
    config = copy.deepcopy(settings.REQUEST_RATE_LIMITS)
    mutate(config)
    return config


class DefaultsTests(SimpleTestCase):
    def test_settings_carry_the_validated_defaults(self):
        self.assertEqual(settings.REQUEST_RATE_LIMITS, load_request_limits(DEFAULTS))
        self.assertEqual(limits_settings.__all__, ["REQUEST_RATE_LIMITS", "REQUEST_RATE_LIMITS_ENABLED"])

    def test_smart_is_on_for_every_scope_and_every_tier_is_used(self):
        scopes = settings.REQUEST_RATE_LIMITS["scopes"]
        self.assertTrue(all(spec["smart_enabled"] for spec in scopes.values()))
        self.assertEqual({spec["tier"] for spec in scopes.values()}, {"p0", "p1", "p2", "p3"})

    def test_user_initiated_auth_and_code_flows_are_p0_and_never_keyed_on_the_ip(self):
        scopes = settings.REQUEST_RATE_LIMITS["scopes"]
        for name in ("auth-sign-in", "auth-code-send", "auth-code-verify", "auth-email-link", "auth-challenge"):
            with self.subTest(scope=name):
                self.assertEqual(scopes[name]["tier"], "p0")
                self.assertNotEqual(scopes[name]["identity"], "ip")
                self.assertIsNotNone(scopes[name]["global_cap"])

    def test_scopes_smart_must_never_tighten_are_fixed(self):
        scopes = settings.REQUEST_RATE_LIMITS["scopes"]
        for name in ("auth-token-refresh", "auth-session", "checkin-scan", "webhook-ses", "checkin-status"):
            with self.subTest(scope=name):
                self.assertTrue(scopes[name]["fixed"])

    def test_todays_rates_seed_the_scopes_that_had_one(self):
        scopes = settings.REQUEST_RATE_LIMITS["scopes"]
        self.assertEqual((scopes["webhook-ses"]["requests"], scopes["webhook-ses"]["period_seconds"]), (600, 60))
        self.assertEqual(scopes["auth-code-verify"]["requests"], 60)
        self.assertEqual(scopes["public-read"]["requests"], 3_000)

    def test_tier_defaults(self):
        tiers = settings.REQUEST_RATE_LIMITS["tiers"]
        self.assertEqual(
            [(tiers[t]["decrease_factor"], tiers[t]["admission_share"]) for t in ("p1", "p2", "p3")],
            [(0.85, 0.9), (0.7, 0.7), (0.5, 0.5)],
        )
        self.assertEqual(settings.REQUEST_RATE_LIMITS["admission"]["p0_reserved_slots"], 2)

    def test_retry_after_is_exposed_to_the_browser(self):
        self.assertIn("Retry-After", settings.CORS_EXPOSE_HEADERS)


class OverrideTests(SimpleTestCase):
    def test_blank_overrides_give_the_defaults(self):
        self.assertEqual(load_request_limits(DEFAULTS, "  "), load_request_limits(DEFAULTS))

    def test_a_value_is_merged_key_by_key(self):
        config = load({"scopes": {"public-read": {"global_cap": 20_000}}, "controller": {"window_seconds": 30}})
        self.assertEqual(config["scopes"]["public-read"]["global_cap"], 20_000)
        self.assertEqual(config["scopes"]["public-read"]["requests"], 3_000)
        self.assertEqual(config["controller"]["window_seconds"], 30)

    def test_routes_and_exemptions_can_be_added_replaced_and_removed(self):
        config = load(
            {
                "routes": {"cms-homepage": "public-heavy", "admin-login": "auth-sign-in", "csp-report": None},
                "exempt": {"cms-embed-block": "Embedded widgets."},
            }
        )
        self.assertEqual(config["routes"]["cms-homepage"], "public-heavy")
        self.assertEqual(config["routes"]["admin-login"], "auth-sign-in")
        self.assertNotIn("csp-report", config["routes"])
        self.assertEqual(config["exempt"]["cms-embed-block"], "Embedded widgets.")

    def test_lists_become_tuples(self):
        config = load({"store": {"shared_backends": ["my.Redis"]}})
        self.assertEqual(config["store"]["shared_backends"], ("my.Redis",))

    def test_bad_overrides_are_refused(self):
        cases = {
            "not json": ("{", "must be valid JSON"),
            "not an object": ("[1]", "must be a JSON object"),
            "NaN": ('{"controller": {"window_seconds": NaN}}', "must be valid JSON"),
            "unknown scope": ('{"scopes": {"nope": {}}}', "scopes.nope is not a request-limit setting"),
            "unknown key": ('{"controller": {"speed": 1}}', "controller.speed is not a request-limit setting"),
            "object expected": ('{"controller": 3}', "controller must be a JSON object"),
        }
        for name, (raw, message) in cases.items():
            with self.subTest(name), self.assertRaisesMessage(ImproperlyConfigured, message):
                load_request_limits(DEFAULTS, raw)


INVALID = {
    "top level": (lambda c: c.pop("abuse"), "(top level) must have exactly the sections"),
    "scopes not object": (lambda c: c.update(scopes=[]), "scopes must be an object"),
    "no scopes": (lambda c: c.update(scopes={}), "scopes must define at least one scope"),
    "scope key": (lambda c: c["scopes"].update({"Bad Key": c["scopes"]["cli"]}), "scopes.Bad Key must be a lower-case"),
    "scope keys": (lambda c: c["scopes"]["cli"].pop("label"), "scopes.cli must have exactly the keys"),
    "scope object": (lambda c: c["scopes"].update(cli=[]), "scopes.cli must be an object"),
    "label": (lambda c: c["scopes"]["cli"].update(label=" "), "scopes.cli.label must be non-empty text"),
    "description": (lambda c: c["scopes"]["cli"].update(description=3), "scopes.cli.description must be text"),
    "tier": (lambda c: c["scopes"]["cli"].update(tier="p9"), "scopes.cli.tier must be one of"),
    "identity": (lambda c: c["scopes"]["cli"].update(identity="cookie"), "scopes.cli.identity must be one of"),
    "requests": (lambda c: c["scopes"]["cli"].update(requests=0), "scopes.cli.requests must be a whole number"),
    "bool requests": (lambda c: c["scopes"]["cli"].update(requests=True), "scopes.cli.requests must be a whole"),
    "period": (lambda c: c["scopes"]["cli"].update(period_seconds=86_401), "scopes.cli.period_seconds must be"),
    "flag": (lambda c: c["scopes"]["cli"].update(fixed="yes"), "scopes.cli.fixed must be true or false"),
    "floor": (lambda c: c["scopes"]["cli"].update(smart_floor=0), "scopes.cli.smart_floor must be a share"),
    "cap": (lambda c: c["scopes"]["cli"].update(global_cap=-1), "scopes.cli.global_cap must be a whole number"),
    "ceiling": (lambda c: c["scopes"]["cli"].update(identity_ceiling=10), "scopes.cli.requests must not be above"),
    "routes not object": (lambda c: c.update(routes=[]), "routes must be an object"),
    "route scope": (lambda c: c["routes"].update(x="nope"), "routes.x must name a scope"),
    "route empty map": (lambda c: c["routes"].update(x={}), "routes.x must name at least one method"),
    "route method": (lambda c: c["routes"].update(x={"get": "cli"}), "routes.x.get must be an upper-case HTTP method"),
    "route map scope": (lambda c: c["routes"].update(x={"GET": "nope"}), "routes.x.GET must name a scope"),
    "exempt reason": (lambda c: c["exempt"].update(x=""), "exempt.x must be non-empty text"),
    "exempt and routed": (
        lambda c: c["exempt"].update({"admin:search": "why"}),
        "exempt.admin:search is also in routes",
    ),
    "tier order": (lambda c: c.update(tiers=dict(reversed(c["tiers"].items()))), "tiers must list exactly the tiers"),
    "p0 keys": (lambda c: c["tiers"]["p0"].update(floor=1), "tiers.p0 must have exactly the keys label"),
    "tier keys": (lambda c: c["tiers"]["p1"].pop("floor"), "tiers.p1 must have exactly the keys"),
    "decrease": (lambda c: c["tiers"]["p3"].update(decrease_factor=1), "tiers.p3.decrease_factor must be a share"),
    "share order": (lambda c: c["tiers"]["p3"].update(admission_share=0.95), "admission_share must not grow"),
    "controller keys": (lambda c: c["controller"].pop("min_requests"), "controller must have exactly the keys"),
    "window": (lambda c: c["controller"].update(window_seconds=0), "controller.window_seconds must be a number"),
    "hold": (lambda c: c["controller"].update(recovery_hold_seconds=-1), "controller.recovery_hold_seconds must"),
    "latency": (lambda c: c["controller"].update(latency_healthy_ms=0), "controller.latency_healthy_ms must be"),
    "latency order": (
        lambda c: c["controller"].update(latency_healthy_ms=5_000),
        "controller.latency_healthy_ms must be below latency_overload_ms",
    ),
    "error order": (
        lambda c: c["controller"].update(error_healthy_share=0.5),
        "controller.error_healthy_share must be below error_overload_share",
    ),
    "inflight": (lambda c: c["controller"].update(inflight_overload_share=2), "inflight_overload_share must be a"),
    "slots": (lambda c: c["admission"].update(concurrency_limit=0), "admission.concurrency_limit must be a whole"),
    "reserve": (lambda c: c["admission"].update(p0_reserved_slots=0), "admission.p0_reserved_slots must be a whole"),
    "reserve size": (lambda c: c["admission"].update(p0_reserved_slots=20), "must be below concurrency_limit"),
    "retry": (lambda c: c["admission"].update(retry_after_seconds=0), "admission.retry_after_seconds must be"),
    "strikes": (lambda c: c["abuse"].update(strikes_to_block=0), "abuse.strikes_to_block must be a whole"),
    "block order": (lambda c: c["abuse"].update(block_base_seconds=1_000), "abuse.block_base_seconds must not be"),
    "mode": (lambda c: c["store"].update(mode="redis"), "store.mode must be one of"),
    "backends": (lambda c: c["store"].update(shared_backends=()), "store.shared_backends must be a non-empty"),
    "heartbeat": (lambda c: c["store"].update(heartbeat_seconds=90), "store.heartbeat_seconds must be below"),
    "prune": (lambda c: c["store"].update(process_prune_seconds=60), "store.process_prune_seconds must not be"),
    "refusal history": (
        lambda c: c["store"].update(refusal_history_minutes=0),
        "store.refusal_history_minutes must be a whole number between 1 and 120",
    ),
    "refusal history size": (
        lambda c: c["store"].update(refusal_history_minutes=121),
        "store.refusal_history_minutes must be a whole number between 1 and 120",
    ),
    "prefix": (lambda c: c["fallback"].update(admin_prefix="admin"), "fallback.admin_prefix must be a path"),
    "fallback scope": (lambda c: c["fallback"].update(cli="nope"), "fallback.cli must name a route scope"),
    "fallback view scope": (
        lambda c: c["fallback"].update(unproven="view-code-verify"),
        "fallback.unproven must name a route scope",
    ),
    "scope not an object": (lambda c: c["scopes"].update(x=[]), "scopes.x must be an object"),
    "view scope parent": (
        lambda c: c["scopes"]["view-code-verify"].update(parent="nope"),
        "scopes.view-code-verify.parent must name a route scope",
    ),
    "view scope parent is a view scope": (
        lambda c: c["scopes"]["view-code-verify"].update(parent="view-cli-read"),
        "scopes.view-code-verify.parent must name a route scope",
    ),
    "view scope parent type": (
        lambda c: c["scopes"]["view-code-verify"].update(parent={"a": 1}),
        "scopes.view-code-verify.parent must name a route scope",
    ),
    "view scope without parent": (
        lambda c: c["scopes"]["view-code-verify"].pop("parent"),
        "scopes.view-code-verify.parent must name a route scope",
    ),
    "parent on a route scope": (
        lambda c: c["scopes"]["public-read"].update(parent="ai"),
        'scopes.public-read.parent is only for a per-view limit (identity "view")',
    ),
    "view scope aggregate": (
        lambda c: c["scopes"]["view-cli-read"].update(global_cap=5),
        "scopes.view-cli-read.global_cap must be null",
    ),
    "route to a view scope": (
        lambda c: c["routes"].update(x="view-cli-read"),
        "routes.x names a per-view limit",
    ),
}


class ValidationTests(SimpleTestCase):
    def test_every_rule(self):
        for name, (mutate, message) in INVALID.items():
            with self.subTest(name), self.assertRaisesMessage(ImproperlyConfigured, message):
                validate_request_limits(broken(mutate))

    def test_a_valid_config_passes(self):
        validate_request_limits(copy.deepcopy(settings.REQUEST_RATE_LIMITS))


class SwitchTests(SimpleTestCase):
    def test_env_switch(self):
        for value, default, expected in (
            ("", True, True),
            ("", False, False),
            ("TRUE", False, True),
            ("off", True, False),
        ):
            with self.subTest(value=value), patch.dict("os.environ", {"REQUEST_RATE_LIMITS_ENABLED": value}):
                self.assertIs(enabled_from_env(default), expected)

    def test_the_limiter_is_off_in_the_test_settings_unless_the_environment_enables_it(self):
        from config.settings.environments import test as test_settings
        from config.settings.environments import unit as unit_settings

        self.assertIs(test_settings.REQUEST_RATE_LIMITS_ENABLED, enabled_from_env(False))
        self.assertIs(unit_settings.REQUEST_RATE_LIMITS_ENABLED, test_settings.REQUEST_RATE_LIMITS_ENABLED)

    def test_the_running_suite_has_it_off(self):
        self.assertFalse(settings.REQUEST_RATE_LIMITS_ENABLED)

    def test_the_concurrency_limit_comes_from_uvicorn(self):
        with patch.dict("os.environ", {"UVICORN_LIMIT_CONCURRENCY": "32"}):
            self.assertEqual(importlib.reload(runtime).ADMISSION["concurrency_limit"], 32)
        with patch.dict("os.environ", {"UVICORN_LIMIT_CONCURRENCY": "many"}):
            with self.assertRaisesMessage(ImproperlyConfigured, "UVICORN_LIMIT_CONCURRENCY must be a whole number"):
                importlib.reload(runtime)
        importlib.reload(runtime)

    def test_the_middleware_runs_after_cors_health_and_authentication(self):
        middleware = settings.MIDDLEWARE
        position = middleware.index("apps.core.middleware.RequestRateLimitMiddleware")
        for name in (
            "corsheaders.middleware.CorsMiddleware",
            "apps.core.middleware.HealthCheckMiddleware",
            "django.contrib.auth.middleware.AuthenticationMiddleware",
        ):
            self.assertLess(middleware.index(name), position)
