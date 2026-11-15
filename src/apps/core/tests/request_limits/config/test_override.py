import copy
import importlib
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from apps.core.tests.request_limits.config.test_settings import DEFAULTS, INVALID, broken, load
from config.settings.base.integrations.request_limits import enabled_from_env
from config.settings.base.integrations.request_limits.defaults import runtime
from config.settings.base.integrations.request_limits.validation import load_request_limits, validate_request_limits


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

    def test_the_running_suite_has_it_off_unless_the_run_switched_it_on(self):
        self.assertIs(settings.REQUEST_RATE_LIMITS_ENABLED, enabled_from_env(False))

    def test_the_concurrency_limit_comes_from_uvicorn(self):
        with patch.dict("os.environ", {"UVICORN_LIMIT_CONCURRENCY": "32"}):
            self.assertEqual(importlib.reload(runtime).ADMISSION["concurrency_limit"], 32)
        with patch.dict("os.environ", {"UVICORN_LIMIT_CONCURRENCY": "many"}):
            with self.assertRaisesMessage(ImproperlyConfigured, "UVICORN_LIMIT_CONCURRENCY must be a whole number"):
                importlib.reload(runtime)
        importlib.reload(runtime)

    def test_the_middleware_runs_after_cors_health_and_sessions_and_before_csrf(self):
        middleware = settings.MIDDLEWARE
        position = middleware.index("apps.core.middleware.RequestRateLimitMiddleware")
        for name in (
            "corsheaders.middleware.CorsMiddleware",
            "apps.core.middleware.HealthCheckMiddleware",
            "django.contrib.sessions.middleware.SessionMiddleware",
        ):
            self.assertLess(middleware.index(name), position)
        self.assertGreater(middleware.index("django.middleware.csrf.CsrfViewMiddleware"), position)
