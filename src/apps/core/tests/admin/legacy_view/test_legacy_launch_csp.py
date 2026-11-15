from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless

from django.db import close_old_connections, connection
from django.http import HttpResponse
from django.test import Client, RequestFactory, TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from apps.core.middleware.csp_middleware import ContentSecurityPolicyMiddleware
from apps.core.services.legacy_access import (
    LegacyViewerAccessDenied,
    exchange_legacy_access_code,
    issue_legacy_access_grant,
)
from apps.event.tests.helpers import make_admin


@override_settings(CSP_REPORT_ONLY=False)
class LegacyLaunchCSPTests(TestCase):
    def test_response_extension_adds_only_the_validated_cloudfront_origin(self):
        def get_response(_request):
            response = HttpResponse("ok", content_type="text/plain")
            response.csp_form_action_origins = (
                "https://d111111abcdef8.cloudfront.net/path-is-discarded",
                "javascript:alert(1)",
            )
            return response

        response = ContentSecurityPolicyMiddleware(get_response)(RequestFactory().get("/admin/legacy-view/"))
        policy = response["Content-Security-Policy"]

        self.assertIn("form-action 'self' https://d111111abcdef8.cloudfront.net", policy)
        self.assertNotIn("path-is-discarded", policy)
        self.assertNotIn("javascript:", policy)
        self.assertIn("object-src 'none'", policy)
        self.assertIn("base-uri 'self'", policy)
        self.assertIn("frame-ancestors 'none'", policy)

    def test_malformed_and_non_https_form_action_origins_are_dropped(self):
        def get_response(_request):
            response = HttpResponse("ok", content_type="text/plain")
            response.csp_form_action_origins = (
                "https://[broken",
                "https://d111111abcdef8.cloudfront.net:not-a-port",
                "http://d111111abcdef8.cloudfront.net",
                None,
            )
            return response

        response = ContentSecurityPolicyMiddleware(get_response)(RequestFactory().get("/admin/legacy-view/"))
        form_action = next(
            directive.strip()
            for directive in response["Content-Security-Policy"].split(";")
            if directive.strip().startswith("form-action")
        )

        self.assertEqual(form_action, "form-action 'self'")


@override_settings(
    LEGACY_VIEW_ENABLED=True,
    LEGACY_ORIGIN_URL="http://172.31.69.63:8080",
    LEGACY_VIEWER_URL="https://d111111abcdef8.cloudfront.net",
    LEGACY_ORIGIN_HEADER_NAME="X-I2G-Legacy-Origin-Secret",
    LEGACY_ORIGIN_HEADER_VALUE="a-random-cloudfront-origin-value-with-32-characters",
)
class LegacyProjectRoutingTests(TestCase):
    def test_real_admin_and_gateway_routes_are_mounted(self):
        self.assertEqual(reverse("admin:core_legacy_view_launch"), "/admin/legacy-view/")
        self.assertEqual(reverse("legacy_view:root"), "/legacy-view/")

        response = self.client.get("/legacy-view/")

        self.assertEqual(response.status_code, 404)
        self.assertNotContains(response, "Legacy read-only", status_code=404)


class LegacyConcurrentExchangeTests(TransactionTestCase):
    @skipUnless(connection.vendor == "postgresql", "Production concurrency semantics require PostgreSQL")
    def test_two_simultaneous_exchanges_have_exactly_one_winner(self):
        user = make_admin(apps=["core"], email="legacy-concurrent@example.com")
        client = Client()
        client.force_login(user)
        request = RequestFactory().post("/admin/legacy-view/")
        request.user = user
        request.session = client.session
        code = issue_legacy_access_grant(request).code
        barrier = Barrier(2)

        def exchange_once():
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                exchange_legacy_access_code(code)
                return "success"
            except LegacyViewerAccessDenied:
                return "denied"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = sorted(executor.map(lambda _attempt: exchange_once(), range(2)))

        self.assertEqual(outcomes, ["denied", "success"])
