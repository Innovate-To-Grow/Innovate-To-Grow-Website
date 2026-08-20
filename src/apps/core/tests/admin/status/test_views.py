from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib import admin
from django.test import TestCase, override_settings
from django.urls import path, reverse

from apps.core.admin.infrastructure_status import get_infrastructure_status_urls
from apps.event.tests.helpers import make_admin, make_superuser


class StatusTestAdminSite(admin.site.__class__):
    def get_urls(self):
        return get_infrastructure_status_urls(self) + super().get_urls()


status_admin_site = StatusTestAdminSite(name="admin")
urlpatterns = [path("admin/", status_admin_site.urls)]

MOCK_DASHBOARD = {
    "available": True,
    "stale": False,
    "reason": "",
    "message": "",
    "fetchedAt": "2026-08-20T10:00:00Z",
    "staleAgeSeconds": 0,
    "cacheState": "fresh",
    "status": {
        "schemaVersion": 1,
        "generatedAt": "2026-08-20T10:00:00Z",
        "partial": False,
        "errors": [],
        "stack": {"name": "i2g-status", "resources": []},
        "services": [],
        "probes": [],
        "alarms": [],
    },
}

DASHBOARD_PATCH = "apps.core.admin.infrastructure_status.views.get_infrastructure_dashboard"


@override_settings(
    ROOT_URLCONF=__name__,
    STATUS_PUBLIC_URL="https://status.i2g.ucmerced.edu/",
)
class InfrastructureStatusAdminViewTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.html_url = reverse("admin:core_infrastructure_status")
        cls.data_url = reverse("admin:core_infrastructure_status_data")

    def test_registration_helper_exposes_stable_routes(self):
        self.assertEqual(self.html_url, "/admin/status/infrastructure/")
        self.assertEqual(self.data_url, "/admin/status/infrastructure/data/")

    def test_anonymous_user_is_redirected_to_admin_login(self):
        response = self.client.get(self.html_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_staff_without_core_grant_is_forbidden_on_html_and_data(self):
        self.client.force_login(make_admin(apps=["cms"], email="cms-status-denied@example.com"))
        for url in (self.html_url, self.data_url):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    @patch(DASHBOARD_PATCH, return_value=MOCK_DASHBOARD)
    def test_core_staff_can_render_unfold_dashboard(self, dashboard):
        self.client.force_login(make_admin(apps=["core"], email="core-status@example.com"))

        response = self.client.get(self.html_url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin/status/infrastructure.html")
        self.assertContains(response, "Infrastructure detail")
        self.assertContains(response, "core/status/infrastructure.css")
        self.assertContains(response, "core/status/infrastructure.js")
        self.assertContains(response, "https://status.i2g.ucmerced.edu/")
        self.assertContains(response, self.data_url)
        self.assertNotContains(response, "90-day uptime")
        self.assertNotContains(response, "Incident history")
        self.assertIn("private", response["Cache-Control"])
        self.assertIn("no-store", response["Cache-Control"])
        dashboard.assert_called_once_with()

    @patch(DASHBOARD_PATCH, return_value=MOCK_DASHBOARD)
    def test_superuser_can_read_json_and_force_refresh(self, dashboard):
        self.client.force_login(make_superuser(email="status-master@example.com"))

        response = self.client.get(self.data_url, {"force": "1"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), MOCK_DASHBOARD)
        self.assertIn("no-store", response["Cache-Control"])
        dashboard.assert_called_once_with(force=True)

    @patch(DASHBOARD_PATCH, return_value=MOCK_DASHBOARD)
    def test_non_force_value_does_not_bypass_cache(self, dashboard):
        self.client.force_login(make_superuser(email="status-no-force@example.com"))
        self.client.get(self.data_url, {"force": "true"})
        dashboard.assert_called_once_with(force=False)

    def test_both_endpoints_are_get_only(self):
        self.client.force_login(make_admin(apps=["core"], email="core-status-post@example.com"))
        for url in (self.html_url, self.data_url):
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url).status_code, 405)

    def test_client_script_never_inserts_upstream_html(self):
        script = Path(settings.BASE_DIR / "apps/core/static/core/status/infrastructure.js").read_text(encoding="utf-8")
        self.assertNotIn("innerHTML", script)
        self.assertIn("textContent", script)
        self.assertIn("requestInFlight", script)
        self.assertIn("Dependency ·", script)
