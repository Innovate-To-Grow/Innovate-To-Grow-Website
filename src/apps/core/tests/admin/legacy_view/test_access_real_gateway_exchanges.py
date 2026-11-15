from datetime import timedelta
from unittest.mock import patch

from django.contrib.sessions.models import Session
from django.http import HttpResponse
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.models import LegacyAccessGrant
from apps.core.services.legacy_access import (
    LEGACY_VIEWER_COOKIE_NAME,
    LEGACY_VIEWER_TTL_SECONDS,
    LegacyViewerAccessDenied,
    clear_legacy_viewer_cookie,
    require_legacy_viewer,
)
from apps.core.tests.admin.legacy_view.test_access import _LegacyAccessAdminCase
from apps.core.tests.admin.legacy_view.test_access import urlpatterns as urlpatterns  # ROOT_URLCONF=__name__ below
from apps.core.tests.legacy_view.proxy.test_transport_and_views import origin_handle


@override_settings(
    ROOT_URLCONF=__name__,
    LEGACY_VIEW_ENABLED=True,
    LEGACY_VIEWER_URL="https://d111111abcdef8.cloudfront.net",
)
class LegacyAccessAdminTests(_LegacyAccessAdminCase):
    @override_settings(
        LEGACY_ORIGIN_URL="http://172.31.69.63:8080",
        LEGACY_ORIGIN_HEADER_NAME="X-I2G-Legacy-Origin-Secret",
        LEGACY_ORIGIN_HEADER_VALUE="a-random-cloudfront-origin-value-with-32-characters",
    )
    def test_real_gateway_exchanges_admin_code_then_serves_read_only_page(self):
        code = self._issue_code()
        viewer = Client(enforce_csrf_checks=True)
        exchange_url = reverse("legacy_gateway_exchange")
        origin_header = {"X-I2G-Legacy-Origin-Secret": "a-random-cloudfront-origin-value-with-32-characters"}

        self.assertEqual(viewer.post(exchange_url, {"code": code}).status_code, 404)
        exchange = viewer.post(exchange_url, {"code": code}, headers=origin_header, secure=True)

        self.assertEqual(exchange.status_code, 303)
        self.assertEqual(exchange["Location"], "/")
        self.assertIn(LEGACY_VIEWER_COOKIE_NAME, viewer.cookies)
        self.assertEqual(viewer.post(exchange_url, {"code": code}, headers=origin_header).status_code, 403)

        origin = origin_handle(
            b"<html><body><form action='/update' method='post'><button>Save</button></form>"
            b"<a href='/about'>About</a></body></html>",
            headers={"Content-Type": "text/html; charset=utf-8"},
        )
        with patch("apps.core.legacy_view.gateway.views.open_legacy_origin", return_value=origin) as open_origin:
            page_url = reverse("legacy_gateway_proxy", kwargs={"legacy_path": "about"})
            self.assertEqual(viewer.get(page_url, secure=True).status_code, 404)
            page = viewer.get(page_url, headers=origin_header, secure=True)
            # The CSRF middleware rejects this browser write before the gateway's
            # GET/HEAD-only check; neither path reaches the legacy origin.
            self.assertEqual(viewer.post(page_url, headers=origin_header, secure=True).status_code, 403)

        self.assertEqual(page.status_code, 200)
        self.assertIn(b"i2g-legacy-read-only-banner", page.content)
        self.assertIn(b'disabled=""', page.content)
        self.assertIn(b"form-action 'none'", page["Content-Security-Policy"].encode())
        self.assertEqual(open_origin.call_count, 1)

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
