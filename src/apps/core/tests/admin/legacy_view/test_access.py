import re

from django.contrib import admin
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import path, reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from apps.core.admin.legacy_view import get_legacy_view_admin_urls
from apps.core.legacy_view.access import (
    LEGACY_ACCESS_CODE_TTL_SECONDS,
    LEGACY_VIEWER_COOKIE_NAME,
    LEGACY_VIEWER_TTL_SECONDS,
)
from apps.core.legacy_view.gateway.views import legacy_access_exchange_gateway, legacy_proxy_view
from apps.core.models import LegacyAccessGrant
from apps.core.views.legacy_access import legacy_access_exchange_view
from apps.event.tests.helpers import make_admin, make_superuser

_MISSING = object()


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
    path("legacy-view/_i2g-auth/real-exchange", legacy_access_exchange_gateway, name="legacy_gateway_exchange"),
    path("legacy-view/<path:legacy_path>", legacy_proxy_view, name="legacy_gateway_proxy"),
    path("unsafe-bare-exchange", legacy_access_exchange_view, name="unsafe_bare_exchange"),
]


class _LegacyAccessAdminCase(TestCase):
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


@override_settings(
    ROOT_URLCONF=__name__,
    LEGACY_VIEW_ENABLED=True,
    LEGACY_VIEWER_URL="https://d111111abcdef8.cloudfront.net",
)
class LegacyAccessAdminTests(_LegacyAccessAdminCase):
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
