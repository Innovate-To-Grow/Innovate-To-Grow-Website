from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.authn.tests.helpers import scrape_admin_form
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
        cache.clear()
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

    @patch("apps.event.admin.current_project.admin.sync_schedule")
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

    @patch("apps.event.admin.current_project.admin.sync_schedule", side_effect=ScheduleSyncError("kaboom"))
    def test_pull_view_failure_shows_error(self, mock_sync):
        CurrentProjectSchedule.objects.create(name="Demo Day")

        response = self.client.post(reverse("admin:event_currentprojectschedule_pull"))

        self.assertRedirects(response, self.changelist_url)
        messages = [str(m) for m in response.wsgi_request._messages]
        self.assertTrue(any("Sync failed for 'Demo Day': kaboom" in m for m in messages))

    @patch("apps.event.admin.current_project.admin.sync_schedule")
    def test_row_action_syncs_a_non_active_schedule(self, mock_sync):
        # Any schedule row (e.g. a previous year's) can be pulled from its own
        # sheet — not only the active one that the changelist "Pull" tool uses.
        CurrentProjectSchedule.objects.create(name="Demo Day")
        archived = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2025", is_active=False)
        mock_sync.return_value = ScheduleSyncStats(sections_created=1, tracks_created=2, slots_created=3)

        response = self.client.get(
            reverse("admin:event_currentprojectschedule_sync_from_google_sheets", args=[archived.pk])
        )

        self.assertRedirects(response, self.changelist_url)
        mock_sync.assert_called_once_with(archived, sync_type="manual")
        messages = [str(m) for m in response.wsgi_request._messages]
        self.assertTrue(any("Synced 'Innovate to Grow 2025'" in m and "3 slots" in m for m in messages))

    @patch("apps.event.admin.current_project.admin.sync_schedule", side_effect=ScheduleSyncError("kaboom"))
    def test_row_action_failure_names_the_schedule(self, mock_sync):
        archived = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2025", is_active=False)

        response = self.client.get(
            reverse("admin:event_currentprojectschedule_sync_from_google_sheets", args=[archived.pk])
        )

        self.assertRedirects(response, self.changelist_url)
        messages = [str(m) for m in response.wsgi_request._messages]
        self.assertTrue(any("Sync failed for 'Innovate to Grow 2025': kaboom" in m for m in messages))

    @patch("apps.event.admin.current_project.admin.sync_schedule")
    def test_row_action_unknown_schedule_shows_error(self, mock_sync):
        response = self.client.get(
            reverse(
                "admin:event_currentprojectschedule_sync_from_google_sheets",
                args=["00000000-0000-0000-0000-000000000000"],
            )
        )

        self.assertRedirects(response, self.changelist_url)
        mock_sync.assert_not_called()
        messages = [str(m) for m in response.wsgi_request._messages]
        self.assertTrue(any("Schedule not found" in m for m in messages))

    @patch("apps.event.admin.current_project.admin.sync_schedule")
    def test_row_action_malformed_object_id_shows_error(self, mock_sync):
        response = self.client.get(
            reverse("admin:event_currentprojectschedule_sync_from_google_sheets", args=["not-a-uuid"])
        )

        self.assertRedirects(response, self.changelist_url)
        mock_sync.assert_not_called()
        messages = [str(m) for m in response.wsgi_request._messages]
        self.assertTrue(any("Schedule not found" in m for m in messages))

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
    def test_change_form_activates_a_schedule_in_one_step_and_archives_auto_sync_on_the_old_one(self):
        previous = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2025", auto_sync_enabled=True)
        incoming = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2026", is_active=False)
        url = reverse("admin:event_currentprojectschedule_change", args=[incoming.pk])
        data = scrape_admin_form(self.client, url, overrides={"is_active": "on", "auto_sync_enabled": "on"})

        response = self.client.post(url, data)

        self.assertEqual(response.status_code, 302, response.content.decode()[:2000])
        previous.refresh_from_db()
        incoming.refresh_from_db()
        self.assertTrue(incoming.is_active)
        self.assertTrue(incoming.auto_sync_enabled)
        self.assertFalse(previous.is_active)
        self.assertFalse(previous.auto_sync_enabled)

    @override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
    def test_change_form_deactivation_archives_auto_sync(self):
        current = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2026", auto_sync_enabled=True)
        url = reverse("admin:event_currentprojectschedule_change", args=[current.pk])
        data = scrape_admin_form(self.client, url)
        data.pop("is_active", None)

        response = self.client.post(url, data)

        self.assertEqual(response.status_code, 302, response.content.decode()[:2000])
        current.refresh_from_db()
        self.assertFalse(current.is_active)
        self.assertFalse(current.auto_sync_enabled)

    def test_changelist_renders_row_sync_action_for_every_schedule(self):
        CurrentProjectSchedule.objects.create(name="Demo Day")
        archived = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2025", is_active=False)

        response = self.client.get(self.changelist_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse("admin:event_currentprojectschedule_sync_from_google_sheets", args=[archived.pk]),
        )

    def test_change_form_renders_detail_sync_action(self):
        archived = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2025", is_active=False)

        response = self.client.get(reverse("admin:event_currentprojectschedule_change", args=[archived.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse("admin:event_currentprojectschedule_sync_from_google_sheets_detail", args=[archived.pk]),
        )

    @patch("apps.event.admin.current_project.admin.sync_schedule")
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

    @patch("apps.event.admin.current_project.admin.sync_schedule")
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

    # The overview (cards, Pull button, Auto Sync form, project tables) acts on
    # the active schedule — or on the only schedule when there is just one, so
    # a row that has not been activated yet is still visible on this page.

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

    def test_changelist_view_with_several_inactive_schedules_shows_no_overview(self):
        CurrentProjectSchedule.objects.create(name="Innovate to Grow 2026", is_active=False)
        CurrentProjectSchedule.objects.create(name="Innovate to Grow 2025", is_active=False)

        response = self.client.get(self.changelist_url)

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["config"])
        self.assertEqual(response.context["current_schedule_name"], "")
        self.assertEqual(list(response.context["current_projects"]), [])
        self.assertContains(response, "No active schedule configured.")

    @patch("apps.event.admin.current_project.admin.sync_schedule")
    def test_pull_view_syncs_the_only_schedule_even_when_inactive(self, mock_sync):
        config = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2026", is_active=False)
        mock_sync.return_value = ScheduleSyncStats(sections_created=1)

        response = self.client.post(reverse("admin:event_currentprojectschedule_pull"))

        self.assertRedirects(response, self.changelist_url)
        mock_sync.assert_called_once_with(config, sync_type="manual")
        messages = [str(m) for m in response.wsgi_request._messages]
        self.assertTrue(any("Synced 'Innovate to Grow 2026'" in m for m in messages))

    @patch("apps.event.admin.current_project.admin.sync_schedule")
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
