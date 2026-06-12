"""Per-app access gating for the projects app's custom admin views.

``admin_site.admin_view`` only enforces is_staff/is_active — Django never runs the
per-app permission model (apps.core.access.user_can_access_app) for these standalone
URLs. Each custom view therefore re-checks ``has_change_permission`` at entry. These
tests exercise the real URLs through the test client: a staff member without the
``projects`` grant gets HTTP 403 (Django renders PermissionDenied as a 403 response),
while a superuser is allowed through.
"""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.event.tests.helpers import make_admin, make_superuser
from apps.projects.models import PastProjectsSheetConfig
from apps.projects.services.sheet_sync import PastProjectSyncStats

_SYNC_PATH = "apps.projects.admin.past_projects_sheet_config.sync_past_projects"


class ProjectsCustomAdminViewAccessTest(TestCase):
    """A grant-less staff member must be 403'd on every custom projects admin URL."""

    def setUp(self):
        cache.clear()
        # Staff member with NO admin_apps grant — must not reach any projects view.
        make_admin(apps=[], email="nogrant@example.com")
        self.client.login(username="nogrant@example.com", password="testpass123")

    def tearDown(self):
        cache.clear()

    def test_pull_view_denied(self):
        url = reverse("admin:projects_pastprojectssheetconfig_pull")
        self.assertEqual(self.client.post(url).status_code, 403)

    def test_save_sync_settings_view_denied_get(self):
        url = reverse("admin:projects_pastprojectssheetconfig_save_sync_settings")
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_save_sync_settings_view_denied_post(self):
        url = reverse("admin:projects_pastprojectssheetconfig_save_sync_settings")
        self.assertEqual(self.client.post(url, {"sync_interval_minutes": "60"}).status_code, 403)

    def test_publish_all_view_denied_get(self):
        url = reverse("admin:projects_publish_all")
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_publish_all_view_denied_post(self):
        url = reverse("admin:projects_publish_all")
        self.assertEqual(self.client.post(url, {"confirmation_text": "publish all"}).status_code, 403)

    def test_import_csv_view_denied_get(self):
        # GET renders the import form — it must be 403'd too, not just the POST.
        url = reverse("admin:projects_import_csv")
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_import_csv_view_denied_post(self):
        url = reverse("admin:projects_import_csv")
        self.assertEqual(self.client.post(url, {"dry_run": "1"}).status_code, 403)

    def test_pull_view_denied_before_side_effect(self):
        # The guard must fire before any sync runs even when a config exists.
        PastProjectsSheetConfig.objects.create(name="Prod", is_active=True)
        url = reverse("admin:projects_pastprojectssheetconfig_pull")
        with patch(_SYNC_PATH) as mock_sync:
            self.assertEqual(self.client.post(url).status_code, 403)
        mock_sync.assert_not_called()


class ProjectsGrantedStaffCustomAdminViewAccessTest(TestCase):
    """A staff member WITH the projects grant is allowed through every custom view."""

    def setUp(self):
        cache.clear()
        make_admin(apps=["projects"], email="projadmin@example.com")
        self.client.login(username="projadmin@example.com", password="testpass123")

    def tearDown(self):
        cache.clear()

    def test_pull_view_allowed(self):
        PastProjectsSheetConfig.objects.create(name="Prod", is_active=True)
        url = reverse("admin:projects_pastprojectssheetconfig_pull")
        with patch(
            _SYNC_PATH,
            return_value=PastProjectSyncStats(
                rows_read=1,
                projects_created=1,
                projects_updated=0,
                projects_deleted=0,
                semesters_touched=1,
                rows_skipped=0,
            ),
        ):
            self.assertNotEqual(self.client.post(url).status_code, 403)

    def test_save_sync_settings_view_allowed(self):
        PastProjectsSheetConfig.objects.create(name="Prod", is_active=True)
        url = reverse("admin:projects_pastprojectssheetconfig_save_sync_settings")
        self.assertNotEqual(self.client.post(url, {"sync_interval_minutes": "60"}).status_code, 403)

    def test_publish_all_view_allowed(self):
        url = reverse("admin:projects_publish_all")
        self.assertNotEqual(self.client.post(url, {"confirmation_text": "publish all"}).status_code, 403)

    def test_import_csv_view_allowed(self):
        url = reverse("admin:projects_import_csv")
        self.assertNotEqual(self.client.get(url).status_code, 403)


class ProjectsSuperuserCustomAdminViewAccessTest(TestCase):
    """The I2G Master (superuser) bypasses the per-app list and is allowed through."""

    def setUp(self):
        cache.clear()
        make_superuser(email="master@example.com")
        self.client.login(username="master@example.com", password="testpass123")

    def tearDown(self):
        cache.clear()

    def test_publish_all_view_allowed(self):
        url = reverse("admin:projects_publish_all")
        self.assertNotEqual(self.client.post(url, {"confirmation_text": "publish all"}).status_code, 403)

    def test_import_csv_view_allowed(self):
        url = reverse("admin:projects_import_csv")
        self.assertNotEqual(self.client.get(url).status_code, 403)
