import re
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.contrib import admin
from django.contrib.sessions.models import Session
from django.db import close_old_connections, connection
from django.http import HttpResponse
from django.test import Client, RequestFactory, TestCase, TransactionTestCase, override_settings
from django.urls import path, reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from apps.core.admin.legacy_view import get_legacy_view_admin_urls
from apps.core.middleware.csp_middleware import ContentSecurityPolicyMiddleware
from apps.core.models import LegacyAccessGrant
from apps.core.services.legacy_access import (
    LEGACY_ACCESS_CODE_TTL_SECONDS,
    LEGACY_VIEWER_COOKIE_NAME,
    LEGACY_VIEWER_TTL_SECONDS,
    LegacyViewerAccessDenied,
    clear_legacy_viewer_cookie,
    exchange_legacy_access_code,
    issue_legacy_access_grant,
    require_legacy_viewer,
)
from apps.core.views.legacy_access import legacy_access_exchange_view
from apps.event.tests.helpers import make_admin, make_superuser


class LegacyTestAdminSite(admin.site.__class__):
    def get_urls(self):
        return get_legacy_view_admin_urls(self) + super().get_urls()


legacy_admin_site = LegacyTestAdminSite(name="admin")


@csrf_exempt
def verified_exchange(request):
    """Stand in for the proxy's successful custom-origin-header gate."""

    request._i2g_legacy_origin_verified = True
    return legacy_access_exchange_view(request)


urlpatterns = [
    path("admin/", legacy_admin_site.urls),
    path("legacy-view/_i2g-auth/exchange", verified_exchange, name="legacy_exchange"),
    path("unsafe-bare-exchange", legacy_access_exchange_view, name="unsafe_bare_exchange"),
]


@override_settings(
    ROOT_URLCONF=__name__,
    LEGACY_VIEW_ENABLED=True,
    LEGACY_VIEWER_URL="https://d111111abcdef8.cloudfront.net",
)
class LegacyAccessAdminTests(TestCase):
    def setUp(self):
        self.user = make_admin(apps=["core"], email="legacy-core@example.com")
        self.client.force_login(self.user)
        self.launch_url = reverse("admin:core_legacy_view_launch")
        self.exchange_url = reverse("legacy_exchange")

    @staticmethod
    def _extract_code(response) -> str:
        match = re.search(rb'name="code" value="([A-Za-z0-9_-]+)"', response.content)
        if not match:
            raise AssertionError("Launch response did not contain an exchange code")
        return match.group(1).decode()

    def _issue_code(self) -> str:
        return self._extract_code(self.client.post(self.launch_url))

    def _exchange_code(self, code: str):
        return self.client.post(self.exchange_url, {"code": code})

    def _viewer_request(self, response):
        session_key = response.cookies[LEGACY_VIEWER_COOKIE_NAME].value
        return RequestFactory().get(
            "/",
            HTTP_COOKIE=f"{LEGACY_VIEWER_COOKIE_NAME}={session_key}",
        )

    def test_admin_route_requires_login_and_core_access(self):
        self.client.logout()
        response = self.client.get(self.launch_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

        self.client.force_login(make_admin(apps=["cms"], email="legacy-denied@example.com"))
        self.assertEqual(self.client.get(self.launch_url).status_code, 403)

        self.client.force_login(make_superuser(email="legacy-master@example.com"))
        self.assertEqual(self.client.get(self.launch_url).status_code, 200)

    def test_launch_form_is_csrf_protected_and_opens_a_new_tab(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        get_response = csrf_client.get(self.launch_url)

        self.assertContains(get_response, 'method="post" target="_blank"')
        self.assertEqual(csrf_client.post(self.launch_url).status_code, 403)

        token = csrf_client.cookies["csrftoken"].value
        post_response = csrf_client.post(
            self.launch_url,
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(post_response.status_code, 200)
        self.assertContains(post_response, 'action="https://d111111abcdef8.cloudfront.net/_i2g-auth/exchange"')
        self.assertContains(post_response, 'id="legacy-view-exchange"')
        self.assertContains(post_response, ".submit()")

    def test_launch_stores_only_a_digest_and_binds_the_admin_session(self):
        before = timezone.now()
        response = self.client.post(self.launch_url)
        code = self._extract_code(response)
        grant = LegacyAccessGrant.objects.get()

        self.assertNotEqual(grant.code_digest, code)
        self.assertNotIn(code, [str(value) for value in grant.__dict__.values()])
        self.assertEqual(grant.source_session_key, self.client.session.session_key)
        self.assertGreater(grant.expires_at, before)
        self.assertLessEqual(
            (grant.expires_at - grant.created_at).total_seconds(),
            LEGACY_ACCESS_CODE_TTL_SECONDS,
        )
        self.assertEqual(
            response.csp_form_action_origins,
            ("https://d111111abcdef8.cloudfront.net",),
        )
        self.assertIn("no-store", response["Cache-Control"])

    def test_exchange_is_single_use_and_sets_a_hardened_one_hour_cookie(self):
        code = self._issue_code()

        response = self._exchange_code(code)

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response["Location"], "/")
        cookie = response.cookies[LEGACY_VIEWER_COOKIE_NAME]
        self.assertTrue(cookie["secure"])
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")
        self.assertEqual(cookie["path"], "/")
        self.assertGreater(int(cookie["max-age"]), 0)
        self.assertLessEqual(int(cookie["max-age"]), LEGACY_VIEWER_TTL_SECONDS)
        self.assertIsNotNone(LegacyAccessGrant.objects.get().consumed_at)

        replay = self._exchange_code(code)
        self.assertEqual(replay.status_code, 403)
        self.assertEqual(replay.content, b"Access denied.")

    def test_invalid_expired_and_replayed_codes_share_the_same_denial(self):
        invalid = self._exchange_code("not-a-real-code")

        code = self._issue_code()
        LegacyAccessGrant.objects.filter(consumed_at__isnull=True).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        expired = self._exchange_code(code)

        self.assertEqual((invalid.status_code, invalid.content), (expired.status_code, expired.content))
        self.assertIn("no-store", expired["Cache-Control"])

    def test_exchange_rejects_direct_mount_without_verified_origin_marker(self):
        code = self._issue_code()

        response = self.client.post(reverse("unsafe_bare_exchange"), {"code": code})

        self.assertEqual(response.status_code, 404)
        self.assertIsNone(LegacyAccessGrant.objects.get().consumed_at)

    def test_exchange_is_csrf_exempt_after_the_verified_gateway(self):
        code = self._issue_code()
        cross_site_client = Client(enforce_csrf_checks=True)

        response = cross_site_client.post(self.exchange_url, {"code": code})

        self.assertEqual(response.status_code, 303)

    def test_viewer_session_revalidates_user_permission(self):
        response = self._exchange_code(self._issue_code())
        request = self._viewer_request(response)
        self.assertEqual(require_legacy_viewer(request).pk, self.user.pk)

        self.user.admin_apps = []
        self.user.save(update_fields=["admin_apps"])
        with self.assertRaises(LegacyViewerAccessDenied):
            require_legacy_viewer(self._viewer_request(response))

    def test_viewer_session_revalidates_active_user(self):
        response = self._exchange_code(self._issue_code())
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        with self.assertRaises(LegacyViewerAccessDenied):
            require_legacy_viewer(self._viewer_request(response))

    def test_viewer_session_revalidates_source_admin_session(self):
        response = self._exchange_code(self._issue_code())
        source_session_key = LegacyAccessGrant.objects.get().source_session_key
        Session.objects.filter(session_key=source_session_key).delete()

        with self.assertRaises(LegacyViewerAccessDenied):
            require_legacy_viewer(self._viewer_request(response))

    def test_viewer_session_enforces_absolute_one_hour_expiry(self):
        response = self._exchange_code(self._issue_code())
        future = timezone.now() + timedelta(seconds=LEGACY_VIEWER_TTL_SECONDS + 1)

        with (
            patch("apps.core.services.legacy_access.sessions.timezone.now", return_value=future),
            self.assertRaises(LegacyViewerAccessDenied),
        ):
            require_legacy_viewer(self._viewer_request(response))

    def test_viewer_lifetime_is_clamped_to_original_admin_session(self):
        source_key = self.client.session.session_key
        source_expiry = timezone.now() + timedelta(seconds=120)
        Session.objects.filter(session_key=source_key).update(expire_date=source_expiry)

        response = self._exchange_code(self._issue_code())
        cookie = response.cookies[LEGACY_VIEWER_COOKIE_NAME]

        self.assertLessEqual(int(cookie["max-age"]), 120)
        grant = LegacyAccessGrant.objects.get()
        self.assertLessEqual(grant.source_session_expires_at, source_expiry)

    def test_denial_helper_expires_the_cookie_with_matching_security_attributes(self):
        response = HttpResponse(status=403)

        clear_legacy_viewer_cookie(response)

        cookie = response.cookies[LEGACY_VIEWER_COOKIE_NAME]
        self.assertEqual(cookie["max-age"], 0)
        self.assertEqual(cookie["path"], "/")
        self.assertTrue(cookie["secure"])
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")

    @override_settings(LEGACY_VIEW_ENABLED=False)
    def test_disabled_flag_hides_launch_and_exchange(self):
        self.assertEqual(self.client.get(self.launch_url).status_code, 404)
        self.assertEqual(self.client.post(self.exchange_url, {"code": "anything"}).status_code, 404)

    @override_settings(LEGACY_VIEWER_URL="https://viewer.example/path")
    def test_invalid_viewer_url_fails_closed_without_issuing_a_code(self):
        response = self.client.post(self.launch_url)

        self.assertEqual(response.status_code, 503)
        self.assertContains(response, "Viewer unavailable", status_code=503)
        self.assertFalse(LegacyAccessGrant.objects.exists())


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
