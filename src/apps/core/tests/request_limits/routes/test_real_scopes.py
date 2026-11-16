from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.core.services.request_limits.runtime import signals
from apps.core.tests.request_limits.routes.test_middleware import URLS

from ..helpers import isolate


@override_settings(REQUEST_RATE_LIMITS_ENABLED=True, ROOT_URLCONF=URLS)
class RealScopesTests(TestCase):
    """The shipped scopes through the real route table."""

    def setUp(self):
        cache.clear()
        isolate(self)
        self.client = APIClient()

    def test_robots_is_exempt_and_the_check_scope_is_per_member_only(self):
        with override_settings(ROOT_URLCONF="config.routing.urls"):
            self.assertEqual({self.client.get("/robots.txt").status_code for _ in range(3)}, {200})
            self.client.get("/authn/session/")
        self.assertIn("auth-session", signals.WINDOW.scopes)
