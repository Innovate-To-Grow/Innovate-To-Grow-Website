import inspect

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from apps.core.tests.request_limits.rules.test_fairness_rules import INVALID, SETTINGS, broken
from config.settings.base.integrations import request_limits as limits_settings
from config.settings.base.integrations.request_limits.validation import validate_request_limits


class ValidationTests(SimpleTestCase):
    def test_the_new_keys_are_validated(self):
        for name, (mutate, message) in INVALID.items():
            with self.subTest(name), self.assertRaisesMessage(ImproperlyConfigured, message):
                validate_request_limits(broken(mutate))

    def test_a_scope_without_a_source_cap_is_valid(self):
        validate_request_limits(broken(lambda c: c["scopes"]["cli"].pop("source_cap")))


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
