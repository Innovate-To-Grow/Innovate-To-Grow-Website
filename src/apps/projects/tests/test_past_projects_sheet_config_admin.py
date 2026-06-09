from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.authn.models import ContactEmail
from apps.projects.admin.past_projects_sheet_config import PastProjectsSheetConfigAdmin
from apps.projects.models import PastProjectsSheetConfig
from apps.projects.services.sheet_sync import PastProjectSyncStats, SheetSyncError

User = get_user_model()

_ADMIN_PATH = "apps.projects.admin.past_projects_sheet_config.sync_past_projects"


def _make_superuser(email="admin@example.com"):
    user = User.objects.create_superuser(password="testpass123", first_name="Admin", last_name="User")
    ContactEmail.objects.create(member=user, email_address=email, email_type="primary", verified=True)
    return user


class SyncErrorShortTest(TestCase):
    def setUp(self):
        self.model_admin = PastProjectsSheetConfigAdmin(PastProjectsSheetConfig, admin.site)

    def test_truncates_long_error(self):
        obj = PastProjectsSheetConfig(sync_error="x" * 200)
        result = self.model_admin.sync_error_short(obj)
        self.assertTrue(result.endswith("..."))
        self.assertEqual(len(result), 83)

    def test_keeps_short_error(self):
        obj = PastProjectsSheetConfig(sync_error="short")
        self.assertEqual(self.model_admin.sync_error_short(obj), "short")

    def test_empty_returns_blank(self):
        obj = PastProjectsSheetConfig(sync_error="")
        self.assertEqual(self.model_admin.sync_error_short(obj), "")


class PullViewTest(TestCase):
    def setUp(self):
        _make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.url = reverse("admin:projects_pastprojectssheetconfig_pull")
        self.changelist = reverse("admin:projects_pastprojectssheetconfig_changelist")

    def test_no_config_shows_error(self):
        response = self.client.post(self.url, follow=True)
        self.assertRedirects(response, self.changelist)
        messages = [m.message for m in response.context["messages"]]
        self.assertTrue(any("No configuration found" in m for m in messages))

    def test_success_reports_stats(self):
        config = PastProjectsSheetConfig.objects.create(name="Prod", is_active=True)
        with patch(
            _ADMIN_PATH,
            return_value=PastProjectSyncStats(
                rows_read=5,
                projects_created=4,
                projects_updated=2,
                projects_deleted=1,
                semesters_touched=2,
                rows_skipped=1,
            ),
        ) as mock_sync:
            response = self.client.post(self.url, follow=True)
        mock_sync.assert_called_once_with(config, sync_type="manual")
        messages = [m.message for m in response.context["messages"]]
        # After the full-replace -> upsert change the banner must surface updates/deletes, not just
        # creates (a steady-state re-sync creates 0 but updates many).
        self.assertTrue(any("Synced: 4 created, 2 updated, 1 deleted" in m for m in messages))
        self.assertTrue(any("1 rows skipped of 5 read" in m for m in messages))

    def test_failure_shows_error(self):
        PastProjectsSheetConfig.objects.create(name="Prod", is_active=True)
        with patch(_ADMIN_PATH, side_effect=SheetSyncError("kaboom")):
            response = self.client.post(self.url, follow=True)
        messages = [m.message for m in response.context["messages"]]
        self.assertTrue(any("Sync failed: kaboom" in m for m in messages))


class SaveSyncSettingsViewTest(TestCase):
    def setUp(self):
        _make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.url = reverse("admin:projects_pastprojectssheetconfig_save_sync_settings")
        self.changelist = reverse("admin:projects_pastprojectssheetconfig_changelist")

    def test_get_redirects(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, self.changelist)

    def test_no_config_shows_error(self):
        response = self.client.post(self.url, {"sync_interval_minutes": "60"}, follow=True)
        messages = [m.message for m in response.context["messages"]]
        self.assertTrue(any("No active configuration" in m for m in messages))

    def test_persists_values(self):
        config = PastProjectsSheetConfig.objects.create(name="Prod", is_active=True)
        self.client.post(self.url, {"auto_sync_enabled": "1", "sync_interval_minutes": "120"})
        config.refresh_from_db()
        self.assertTrue(config.auto_sync_enabled)
        self.assertEqual(config.sync_interval_minutes, 120)

    def test_clamps_interval(self):
        config = PastProjectsSheetConfig.objects.create(name="Prod", is_active=True)
        self.client.post(self.url, {"sync_interval_minutes": "999999"})
        config.refresh_from_db()
        self.assertEqual(config.sync_interval_minutes, 10080)

    def test_invalid_interval_keeps_existing(self):
        config = PastProjectsSheetConfig.objects.create(name="Prod", is_active=True, sync_interval_minutes=1440)
        self.client.post(self.url, {"sync_interval_minutes": "abc"})
        config.refresh_from_db()
        self.assertEqual(config.sync_interval_minutes, 1440)


class ChangelistViewTest(TestCase):
    def setUp(self):
        _make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.changelist = reverse("admin:projects_pastprojectssheetconfig_changelist")

    def test_renders_pull_button_and_google_card_without_config(self):
        response = self.client.get(self.changelist)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pull Past Projects")
        self.assertContains(response, "No active Google service account configured.")
        self.assertContains(response, "No active configuration.")
        self.assertIsNone(response.context["config"])
        self.assertFalse(response.context["google_configured"])

    def test_with_config_exposes_context(self):
        config = PastProjectsSheetConfig.objects.create(name="Prod", is_active=True)
        response = self.client.get(self.changelist)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["config"], config)
        self.assertIn("pull_url", response.context)
        self.assertIn("save_sync_settings_url", response.context)

    def test_has_no_delete_permission(self):
        model_admin = PastProjectsSheetConfigAdmin(PastProjectsSheetConfig, admin.site)
        self.assertFalse(model_admin.has_delete_permission(request=None))
