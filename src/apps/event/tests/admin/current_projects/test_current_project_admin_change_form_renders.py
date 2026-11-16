from unittest.mock import patch

from django.urls import reverse

from apps.core.models import GoogleCredentialConfig
from apps.event.models import (
    CurrentProject,
    CurrentProjectSchedule,
    EventScheduleSection,
    EventScheduleTrack,
)
from apps.event.services import ScheduleSyncStats
from apps.event.tests.admin.current_projects.test_current_project_admin import _CurrentProjectScheduleAdminCase


class CurrentProjectScheduleAdminTest(_CurrentProjectScheduleAdminCase):
    def test_change_form_renders_detail_sync_action(self):
        archived = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2025", is_active=False)

        response = self.client.get(reverse("admin:event_currentprojectschedule_change", args=[archived.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse("admin:event_currentprojectschedule_sync_from_google_sheets_detail", args=[archived.pk]),
        )

    @patch("apps.event.admin.schedule.sheet_pull.sync_schedule")
    def test_detail_action_syncs_and_returns_to_the_change_form(self, mock_sync):
        archived = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2025", is_active=False)
        mock_sync.return_value = ScheduleSyncStats(sections_created=1)

        response = self.client.get(
            reverse("admin:event_currentprojectschedule_sync_from_google_sheets_detail", args=[archived.pk])
        )

        self.assertRedirects(response, reverse("admin:event_currentprojectschedule_change", args=[archived.pk]))
        mock_sync.assert_called_once_with(archived, sync_type="manual")
        messages = [str(m) for m in response.wsgi_request._messages]
        self.assertTrue(any("Synced 'Innovate to Grow 2025'" in m for m in messages))

    @patch("apps.event.admin.schedule.sheet_pull.sync_schedule")
    def test_detail_action_unknown_schedule_returns_to_changelist(self, mock_sync):
        response = self.client.get(
            reverse("admin:event_currentprojectschedule_sync_from_google_sheets_detail", args=["not-a-uuid"])
        )

        self.assertRedirects(response, self.changelist_url)
        mock_sync.assert_not_called()

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

    def test_changelist_view_shows_the_only_schedule_even_when_inactive(self):
        config = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2026", is_active=False)
        project = CurrentProject.objects.create(
            schedule=config, class_code="CAP", team_number="CAP-1", project_title="Alpha"
        )

        response = self.client.get(self.changelist_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["config"], config)
        self.assertEqual(response.context["current_schedule_name"], "Innovate to Grow 2026")
        self.assertEqual([p.pk for p in response.context["current_projects"]], [project.pk])
        self.assertContains(response, "Pull Current Projects &amp; Schedule (only schedule)")
        self.assertContains(response, "Auto Sync (only schedule)")
        self.assertContains(response, "shown because it is the only schedule")
        self.assertNotContains(response, "Schedule (active)")

    def test_changelist_view_with_several_schedules_shows_only_the_active_one(self):
        active = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2026")
        archived = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2025", is_active=False)
        CurrentProject.objects.create(schedule=archived, class_code="CAP", team_number="CAP-9", project_title="Old")

        response = self.client.get(self.changelist_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["config"], active)
        self.assertEqual(response.context["current_schedule_name"], "Innovate to Grow 2026")
        self.assertEqual(list(response.context["current_projects"]), [])
        self.assertContains(response, "Pull Current Projects &amp; Schedule (active)")
        self.assertContains(response, "Auto Sync (active schedule)")
        self.assertNotContains(response, "only schedule")
