from unittest.mock import patch

from django.urls import reverse

from apps.event.models import (
    CurrentProjectSchedule,
)
from apps.event.services import ScheduleSyncStats
from apps.event.tests.admin.current_projects.test_current_project_admin import _CurrentProjectScheduleAdminCase


class CurrentProjectScheduleAdminTest(_CurrentProjectScheduleAdminCase):
    def test_changelist_view_with_several_inactive_schedules_shows_no_overview(self):
        CurrentProjectSchedule.objects.create(name="Innovate to Grow 2026", is_active=False)
        CurrentProjectSchedule.objects.create(name="Innovate to Grow 2025", is_active=False)

        response = self.client.get(self.changelist_url)

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["config"])
        self.assertEqual(response.context["current_schedule_name"], "")
        self.assertEqual(list(response.context["current_projects"]), [])
        self.assertContains(response, "No active schedule configured.")

    @patch("apps.event.admin.schedule.sheet_pull.sync_schedule")
    def test_pull_view_syncs_the_only_schedule_even_when_inactive(self, mock_sync):
        config = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2026", is_active=False)
        mock_sync.return_value = ScheduleSyncStats(sections_created=1)

        response = self.client.post(reverse("admin:event_currentprojectschedule_pull"))

        self.assertRedirects(response, self.changelist_url)
        mock_sync.assert_called_once_with(config, sync_type="manual")
        messages = [str(m) for m in response.wsgi_request._messages]
        self.assertTrue(any("Synced 'Innovate to Grow 2026'" in m for m in messages))

    @patch("apps.event.admin.schedule.sheet_pull.sync_schedule")
    def test_pull_view_with_several_inactive_schedules_shows_error(self, mock_sync):
        CurrentProjectSchedule.objects.create(name="Innovate to Grow 2026", is_active=False)
        CurrentProjectSchedule.objects.create(name="Innovate to Grow 2025", is_active=False)

        response = self.client.post(reverse("admin:event_currentprojectschedule_pull"))

        self.assertRedirects(response, self.changelist_url)
        mock_sync.assert_not_called()
        messages = [str(m) for m in response.wsgi_request._messages]
        self.assertTrue(any("No configuration found" in m for m in messages))

    def test_save_sync_settings_updates_the_only_schedule_even_when_inactive(self):
        config = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2026", is_active=False)

        response = self.client.post(
            reverse("admin:event_currentprojectschedule_save_sync_settings"),
            {"auto_sync_enabled": "1", "sync_interval_minutes": "15"},
        )

        self.assertRedirects(response, self.changelist_url)
        config.refresh_from_db()
        self.assertTrue(config.auto_sync_enabled)
        self.assertEqual(config.sync_interval_minutes, 15)
        self.assertFalse(config.is_active)

    def test_save_sync_settings_with_several_inactive_schedules_shows_error(self):
        first = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2026", is_active=False)
        second = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2025", is_active=False)

        response = self.client.post(
            reverse("admin:event_currentprojectschedule_save_sync_settings"),
            {"auto_sync_enabled": "1", "sync_interval_minutes": "15"},
        )

        self.assertRedirects(response, self.changelist_url)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.auto_sync_enabled)
        self.assertFalse(second.auto_sync_enabled)
        messages = [str(m) for m in response.wsgi_request._messages]
        self.assertTrue(any("No active configuration to update" in m for m in messages))
