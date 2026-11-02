"""System checks for obviously broken request-limit configuration."""

from django.conf import settings
from django.test import SimpleTestCase, override_settings

from apps.core.checks import REQUEST_LIMIT_MIDDLEWARE, check_request_limits
from apps.core.services.request_limits import register_scope

from .helpers import isolate


def ids(problems):
    return [problem.id for problem in problems]


class RequestLimitCheckTests(SimpleTestCase):
    def setUp(self):
        isolate(self)

    @override_settings(REQUEST_RATE_LIMITS_ENABLED=True)
    def test_the_shipped_configuration_passes(self):
        self.assertEqual(check_request_limits(), [])

    @override_settings(REQUEST_RATE_LIMITS_ENABLED="yes")
    def test_the_switch_must_be_a_boolean(self):
        self.assertEqual(ids(check_request_limits()), ["core.E010"])

    def test_enabled_without_the_middleware_warns(self):
        middleware = [name for name in settings.MIDDLEWARE if name != REQUEST_LIMIT_MIDDLEWARE]
        with override_settings(MIDDLEWARE=middleware, REQUEST_RATE_LIMITS_ENABLED=True):
            self.assertEqual(ids(check_request_limits()), ["core.W001"])
        with override_settings(MIDDLEWARE=middleware, REQUEST_RATE_LIMITS_ENABLED=False):
            self.assertEqual(check_request_limits(), [])

    def test_the_middleware_before_cors_health_or_auth_is_an_error(self):
        middleware = [
            REQUEST_LIMIT_MIDDLEWARE,
            *(name for name in settings.MIDDLEWARE if name != REQUEST_LIMIT_MIDDLEWARE),
        ]
        with override_settings(MIDDLEWARE=middleware):
            problems = check_request_limits()
        self.assertEqual(ids(problems), ["core.E008"])
        for name in ("CorsMiddleware", "HealthCheckMiddleware", "AuthenticationMiddleware"):
            self.assertIn(name, problems[0].msg)

    def test_a_registration_naming_an_unknown_scope_is_an_error(self):
        register_scope("some:view", {"GET": "public-read", "POST": "nope"})
        register_scope("other:view", "public-read")
        problems = check_request_limits()
        self.assertEqual(ids(problems), ["core.E009"])
        self.assertIn("some:view", problems[0].msg)
        self.assertNotIn("other:view", problems[0].msg)

    @override_settings(REQUEST_RATE_LIMITS_ENABLED=True, CORS_EXPOSE_HEADERS=[])
    def test_an_unreadable_retry_after_warns(self):
        self.assertEqual(ids(check_request_limits()), ["core.W002"])

    @override_settings(REQUEST_RATE_LIMITS_ENABLED=False, CORS_EXPOSE_HEADERS=[])
    def test_off_needs_no_exposed_header(self):
        self.assertEqual(check_request_limits(), [])
