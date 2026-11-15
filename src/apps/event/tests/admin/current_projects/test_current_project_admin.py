from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.authn.tests.helpers import scrape_admin_form
from apps.event.models import (
    CurrentProjectSchedule,
)
from apps.event.services import ScheduleSyncError, ScheduleSyncStats
from apps.event.tests.helpers import make_superuser


class _CurrentProjectScheduleAdminCase(TestCase):
    def setUp(self):
        cache.clear()
        self.admin_user = make_superuser(email="schedule-admin@example.com")
        self.client.login(username="schedule-admin@example.com", password="testpass123")
        self.changelist_url = reverse("admin:event_currentprojectschedule_changelist")


class CurrentProjectScheduleAdminTest(_CurrentProjectScheduleAdminCase):
    def test_sync_error_short_truncates_long_messages(self):
        from apps.event.admin.schedule.project_schedule import CurrentProjectScheduleAdmin

        admin_instance = CurrentProjectScheduleAdmin(CurrentProjectSchedule, None)
        long_error = "x" * 200
        short = admin_instance.sync_error_short(CurrentProjectSchedule(sync_error=long_error))
        self.assertEqual(short, "x" * 80 + "...")

    def test_sync_error_short_keeps_short_messages(self):
        from apps.event.admin.schedule.project_schedule import CurrentProjectScheduleAdmin

        admin_instance = CurrentProjectScheduleAdmin(CurrentProjectSchedule, None)
        result = admin_instance.sync_error_short(CurrentProjectSchedule(sync_error="boom"))
        self.assertEqual(result, "boom")

    def test_sync_error_short_empty_returns_blank(self):
        from apps.event.admin.schedule.project_schedule import CurrentProjectScheduleAdmin

        admin_instance = CurrentProjectScheduleAdmin(CurrentProjectSchedule, None)
        self.assertEqual(admin_instance.sync_error_short(CurrentProjectSchedule(sync_error="")), "")

    def test_pull_view_no_config_shows_error(self):
        response = self.client.post(reverse("admin:event_currentprojectschedule_pull"))

        self.assertRedirects(response, self.changelist_url)
        messages = list(response.wsgi_request._messages)
        self.assertTrue(any("No configuration found" in str(m) for m in messages))

    @patch("apps.event.admin.schedule.sheet_pull.sync_schedule")
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

    @patch("apps.event.admin.schedule.sheet_pull.sync_schedule", side_effect=ScheduleSyncError("kaboom"))
    def test_pull_view_failure_shows_error(self, mock_sync):
        CurrentProjectSchedule.objects.create(name="Demo Day")

        response = self.client.post(reverse("admin:event_currentprojectschedule_pull"))

        self.assertRedirects(response, self.changelist_url)
        messages = [str(m) for m in response.wsgi_request._messages]
        self.assertTrue(any("Sync failed for 'Demo Day': kaboom" in m for m in messages))

    @patch("apps.event.admin.schedule.sheet_pull.sync_schedule")
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

    @patch("apps.event.admin.schedule.sheet_pull.sync_schedule", side_effect=ScheduleSyncError("kaboom"))
    def test_row_action_failure_names_the_schedule(self, mock_sync):
        archived = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2025", is_active=False)

        response = self.client.get(
            reverse("admin:event_currentprojectschedule_sync_from_google_sheets", args=[archived.pk])
        )

        self.assertRedirects(response, self.changelist_url)
        messages = [str(m) for m in response.wsgi_request._messages]
        self.assertTrue(any("Sync failed for 'Innovate to Grow 2025': kaboom" in m for m in messages))

    @patch("apps.event.admin.schedule.sheet_pull.sync_schedule")
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

    @patch("apps.event.admin.schedule.sheet_pull.sync_schedule")
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
