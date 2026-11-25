"""Access to the projects app's custom admin views.

Each URL is wrapped in ``admin_site.admin_view``, so a regular member is redirected to the admin login before the view
runs and nothing happens. Each view also re-checks the ModelAdmin's ``has_change_permission`` itself (defence in depth),
which is exercised by calling the view directly with a non-Admin request. Every Admin is allowed through.
"""

from unittest.mock import patch

from django.contrib import admin
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.event.tests.helpers import make_admin, make_member
from apps.projects.models import PastProjectsSheetConfig, Semester
from apps.projects.services.sheet_sync import PastProjectSyncStats

_SYNC_PATH = "apps.projects.admin.past_projects_sheet_config.sync_past_projects"


class ProjectsCustomAdminViewNonAdminTest(TestCase):
    """A regular member is redirected to the login page on every custom projects admin URL."""

    def setUp(self):
        cache.clear()
        make_member(email="plain@example.com")
        self.client.login(username="plain@example.com", password="testpass123")

    def tearDown(self):
        cache.clear()

    def assertSentToLogin(self, response):
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_every_custom_url_redirects_to_the_login(self):
        cases = [
            ("get", "admin:projects_pastprojectssheetconfig_save_sync_settings", {}),
            ("post", "admin:projects_pastprojectssheetconfig_save_sync_settings", {"sync_interval_minutes": "60"}),
            ("get", "admin:projects_publish_all", {}),
            ("post", "admin:projects_publish_all", {"confirmation_text": "publish all"}),
            ("get", "admin:projects_import_csv", {}),
            ("post", "admin:projects_import_csv", {"dry_run": "1"}),
        ]
        for method, name, data in cases:
            with self.subTest(method=method, url=name):
                self.assertSentToLogin(getattr(self.client, method)(reverse(name), data))

    def test_pull_view_redirects_before_any_side_effect(self):
        PastProjectsSheetConfig.objects.create(name="Prod", is_active=True)
        Semester.objects.create(year=2025, season=1, is_published=False)
        with patch(_SYNC_PATH) as mock_sync:
            self.assertSentToLogin(self.client.post(reverse("admin:projects_pastprojectssheetconfig_pull")))
        mock_sync.assert_not_called()
        self.client.post(reverse("admin:projects_publish_all"), {"confirmation_text": "publish all"})
        self.assertFalse(Semester.objects.filter(is_published=True).exists())

    def test_the_views_refuse_a_non_admin_even_when_called_directly(self):
        request = RequestFactory().post("/")
        request.user = make_member(email="direct@example.com")
        config_admin = admin.site._registry[PastProjectsSheetConfig]
        semester_admin = admin.site._registry[Semester]
        views = [
            config_admin.pull_view,
            config_admin.save_sync_settings_view,
            semester_admin.publish_all_view,
            semester_admin.import_csv_view,
        ]
        for view in views:
            with self.subTest(view=view.__name__), self.assertRaises(PermissionDenied):
                view(request)


class ProjectsAdminCustomAdminViewAccessTest(TestCase):
    """Any Admin is allowed through every custom view."""

    def setUp(self):
        cache.clear()
        make_admin(email="projadmin@example.com")
        self.client.login(username="projadmin@example.com", password="testpass123")

    def tearDown(self):
        cache.clear()

    def test_pull_view_allowed(self):
        PastProjectsSheetConfig.objects.create(name="Prod", is_active=True)
        url = reverse("admin:projects_pastprojectssheetconfig_pull")
        stats = PastProjectSyncStats(
            rows_read=1,
            projects_created=1,
            projects_updated=0,
            projects_deleted=0,
            semesters_touched=1,
            rows_skipped=0,
        )
        with patch(_SYNC_PATH, return_value=stats) as mock_sync:
            response = self.client.post(url)
        self.assertRedirects(response, reverse("admin:projects_pastprojectssheetconfig_changelist"))
        mock_sync.assert_called_once()

    def test_save_sync_settings_view_allowed(self):
        PastProjectsSheetConfig.objects.create(name="Prod", is_active=True)
        url = reverse("admin:projects_pastprojectssheetconfig_save_sync_settings")
        self.client.post(url, {"sync_interval_minutes": "60"})
        self.assertEqual(PastProjectsSheetConfig.objects.get().sync_interval_minutes, 60)

    def test_publish_all_view_allowed(self):
        Semester.objects.create(year=2025, season=1, is_published=False)
        url = reverse("admin:projects_publish_all")
        self.client.post(url, {"confirmation_text": "publish all"})
        self.assertTrue(Semester.objects.get().is_published)

    def test_import_csv_view_allowed(self):
        url = reverse("admin:projects_import_csv")
        self.assertEqual(self.client.get(url).status_code, 200)
