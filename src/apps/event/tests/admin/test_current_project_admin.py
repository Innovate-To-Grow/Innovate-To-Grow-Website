from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.core.models import GoogleCredentialConfig
from apps.event.models import (
    CurrentProject,
    CurrentProjectSchedule,
    EventScheduleSection,
    EventScheduleTrack,
)
from apps.event.services import ScheduleSyncError, ScheduleSyncStats
from apps.event.tests.helpers import make_superuser


class CurrentProjectScheduleAdminTest(TestCase):
    def setUp(self):
        self.admin_user = make_superuser(email="schedule-admin@example.com")
        self.client.login(username="schedule-admin@example.com", password="testpass123")
        self.changelist_url = reverse("admin:event_currentprojectschedule_changelist")

    def test_sync_error_short_truncates_long_messages(self):
        from apps.event.admin.current_project import CurrentProjectScheduleAdmin

        admin_instance = CurrentProjectScheduleAdmin(CurrentProjectSchedule, None)
        long_error = "x" * 200
        short = admin_instance.sync_error_short(CurrentProjectSchedule(sync_error=long_error))
        self.assertEqual(short, "x" * 80 + "...")

    def test_sync_error_short_keeps_short_messages(self):
        from apps.event.admin.current_project import CurrentProjectScheduleAdmin

        admin_instance = CurrentProjectScheduleAdmin(CurrentProjectSchedule, None)
        result = admin_instance.sync_error_short(CurrentProjectSchedule(sync_error="boom"))
        self.assertEqual(result, "boom")

    def test_sync_error_short_empty_returns_blank(self):
        from apps.event.admin.current_project import CurrentProjectScheduleAdmin

        admin_instance = CurrentProjectScheduleAdmin(CurrentProjectSchedule, None)
        self.assertEqual(admin_instance.sync_error_short(CurrentProjectSchedule(sync_error="")), "")

    def test_pull_view_no_config_shows_error(self):
        response = self.client.post(reverse("admin:event_currentprojectschedule_pull"))

        self.assertRedirects(response, self.changelist_url)
        messages = list(response.wsgi_request._messages)
        self.assertTrue(any("No configuration found" in str(m) for m in messages))

    @patch("apps.event.admin.current_project.sync_schedule")
    def test_pull_view_success_reports_stats(self, mock_sync):
        config = CurrentProjectSchedule.objects.create(name="Demo Day")
        mock_sync.return_value = ScheduleSyncStats(
            sections_created=2,
            tracks_created=3,
            slots_created=4,
            unmatched_slots=1,
        )

        response = self.client.post(reverse("admin:event_currentprojectschedule_pull"))

        self.assertRedirects(response, self.changelist_url)
        mock_sync.assert_called_once_with(config, sync_type="manual")
        messages = [str(m) for m in response.wsgi_request._messages]
        self.assertTrue(any("2 sections" in m and "3 tracks" in m and "4 slots" in m for m in messages))

    @patch("apps.event.admin.current_project.sync_schedule", side_effect=ScheduleSyncError("kaboom"))
    def test_pull_view_failure_shows_error(self, mock_sync):
        CurrentProjectSchedule.objects.create(name="Demo Day")

        response = self.client.post(reverse("admin:event_currentprojectschedule_pull"))

        self.assertRedirects(response, self.changelist_url)
        messages = [str(m) for m in response.wsgi_request._messages]
        self.assertTrue(any("Sync failed: kaboom" in m for m in messages))

    def test_save_sync_settings_get_redirects(self):
        response = self.client.get(reverse("admin:event_currentprojectschedule_save_sync_settings"))
        self.assertRedirects(response, self.changelist_url)

    def test_save_sync_settings_no_config_shows_error(self):
        response = self.client.post(reverse("admin:event_currentprojectschedule_save_sync_settings"), {})

        self.assertRedirects(response, self.changelist_url)
        messages = [str(m) for m in response.wsgi_request._messages]
        self.assertTrue(any("No active configuration to update" in m for m in messages))

    def test_save_sync_settings_persists_values(self):
        config = CurrentProjectSchedule.objects.create(name="Demo Day")

        response = self.client.post(
            reverse("admin:event_currentprojectschedule_save_sync_settings"),
            {"auto_sync_enabled": "1", "sync_interval_minutes": "30"},
        )

        self.assertRedirects(response, self.changelist_url)
        config.refresh_from_db()
        self.assertTrue(config.auto_sync_enabled)
        self.assertEqual(config.sync_interval_minutes, 30)
        messages = [str(m) for m in response.wsgi_request._messages]
        self.assertTrue(any("Auto-sync settings saved" in m for m in messages))

    def test_save_sync_settings_clamps_interval(self):
        config = CurrentProjectSchedule.objects.create(name="Demo Day", sync_interval_minutes=60)

        self.client.post(
            reverse("admin:event_currentprojectschedule_save_sync_settings"),
            {"auto_sync_enabled": "0", "sync_interval_minutes": "99999"},
        )

        config.refresh_from_db()
        self.assertFalse(config.auto_sync_enabled)
        self.assertEqual(config.sync_interval_minutes, 1440)

    def test_save_sync_settings_invalid_interval_keeps_existing(self):
        config = CurrentProjectSchedule.objects.create(name="Demo Day", sync_interval_minutes=45)

        self.client.post(
            reverse("admin:event_currentprojectschedule_save_sync_settings"),
            {"auto_sync_enabled": "1", "sync_interval_minutes": "not-a-number"},
        )

        config.refresh_from_db()
        self.assertEqual(config.sync_interval_minutes, 45)

    def test_changelist_view_without_config_uses_empty_context(self):
        google_config = GoogleCredentialConfig.load()
        google_config.is_configured  # noqa: B018 - ensure attribute resolvable

        response = self.client.get(self.changelist_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_schedule_name"], "")
        self.assertEqual(list(response.context["current_projects"]), [])
        self.assertEqual(list(response.context["non_presenting_projects"]), [])
        self.assertEqual(list(response.context["winners"]), [])
        self.assertIn("google_configured", response.context)

    def test_changelist_view_with_config_splits_projects_and_winners(self):
        config = CurrentProjectSchedule.objects.create(name="Demo Day")
        presenting = CurrentProject.objects.create(
            schedule=config,
            class_code="CAP",
            team_number="CAP-1",
            project_title="Alpha",
            is_presenting=True,
        )
        non_presenting = CurrentProject.objects.create(
            schedule=config,
            class_code="CAP",
            team_number="CAP-2",
            project_title="Beta",
            is_presenting=False,
        )
        section = EventScheduleSection.objects.create(config=config, code="CAP", label="CAP")
        EventScheduleTrack.objects.create(section=section, track_number=1, winner="Winning Team")

        response = self.client.get(self.changelist_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_schedule_name"], "Demo Day")
        self.assertEqual([p.pk for p in response.context["current_projects"]], [presenting.pk])
        self.assertEqual([p.pk for p in response.context["non_presenting_projects"]], [non_presenting.pk])
        winners = list(response.context["winners"])
        self.assertEqual(len(winners), 1)
        self.assertEqual(winners[0].winner, "Winning Team")
