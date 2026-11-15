from unittest.mock import patch

from apps.event.models import (
    CurrentProject,
    CurrentProjectSchedule,
    EventScheduleSlot,
)
from apps.event.services import ScheduleSyncError, sync_schedule
from apps.event.tests.services.schedule_sync.test_schedule_sync import _ScheduleSyncServiceCase


class ScheduleSyncServiceTest(_ScheduleSyncServiceCase):
    def test_resync_with_blank_order_drops_slot_and_marks_non_presenting(self):
        tracks = [{"Track": 1, "Room": "Granite", "Class": "CAP", "Topic": "FoodTech"}]
        row = {"Track": 1, "Order": 1, "Class": "CAP", "Team#": "CAP-101", "Team Name": "Alpha", "Project Title": "A"}
        sync_schedule(self.config, tracks_records=tracks, projects_records=[row])
        self.assertEqual(EventScheduleSlot.objects.count(), 1)

        sync_schedule(self.config, tracks_records=tracks, projects_records=[{**row, "Track": "", "Order": ""}])

        self.assertEqual(EventScheduleSlot.objects.count(), 0)
        self.assertFalse(CurrentProject.objects.get(team_number="CAP-101").is_presenting)

    def test_fall_rows_become_non_presenting_projects_without_slots(self):
        tracks = [{"Track": 1, "Room": "Granite", "Class": "CAP", "Topic": "FoodTech"}]
        projects = [
            {
                "Track": 1,
                "Order": 1,
                "Class": "CAP",
                "Team#": "CAP-101",
                "Team Name": "Alpha",
                "Project Title": "Smart Farm",
            },
            {
                "Track": "(fall)",
                "Order": 2,
                "Class": "CAP",
                "Team#": "CAP-201",
                "Team Name": "Beta",
                "Project Title": "Archived Fall Project",
            },
            {
                "Track": 1,
                "Order": "(fall)",
                "Class": "CAP",
                "Team#": "CAP-301",
                "Team Name": "Gamma",
                "Project Title": "Another Fall Project",
            },
        ]

        stats = sync_schedule(self.config, tracks_records=tracks, projects_records=projects)

        self.assertEqual(stats.slots_created, 1)
        self.assertEqual(CurrentProject.objects.filter(schedule=self.config).count(), 3)

        presenting = CurrentProject.objects.get(team_number="CAP-101")
        self.assertTrue(presenting.is_presenting)

        fall_track = CurrentProject.objects.get(team_number="CAP-201")
        self.assertFalse(fall_track.is_presenting)

        fall_order = CurrentProject.objects.get(team_number="CAP-301")
        self.assertFalse(fall_order.is_presenting)

        self.assertFalse(
            EventScheduleSlot.objects.filter(track__section__config=self.config, team_number="CAP-201").exists()
        )
        self.assertFalse(
            EventScheduleSlot.objects.filter(track__section__config=self.config, team_number="CAP-301").exists()
        )

    def test_sync_saves_team_with_only_team_number(self):
        tracks = [{"Track": 1, "Room": "Granite", "Class": "CAP", "Topic": "FoodTech"}]
        projects = [
            {
                "Track": 1,
                "Order": 1,
                "Class": "CAP",
                "Team#": "CAP-101",
                "Team Name": "Alpha",
                "Project Title": "Smart Farm",
                "Student Names": "Ada, Ben",
            },
            {
                "Track": 1,
                "Order": 2,
                "Class": "CAP",
                "Team#": "CAP-777",
            },
        ]

        sync_schedule(self.config, tracks_records=tracks, projects_records=projects)

        sparse = CurrentProject.objects.get(team_number="CAP-777")
        self.assertEqual(sparse.project_title, "")
        self.assertEqual(sparse.student_names, "")
        self.assertTrue(sparse.is_presenting)

    def test_sync_raises_when_no_config(self):
        empty_config = CurrentProjectSchedule()
        with self.assertRaises(ScheduleSyncError):
            sync_schedule(empty_config)

    @patch("apps.event.services.schedule_sync.GoogleCredentialConfig.load")
    @patch("gspread.service_account_from_dict")
    def test_sync_surfaces_sheet_open_errors(self, mock_service_account, mock_load_credentials):
        mock_service_account.side_effect = RuntimeError("boom")
        mock_load_credentials.return_value.is_configured = True
        mock_load_credentials.return_value.get_credentials_info.return_value = {"client_email": "test@example.com"}
        self.config.sheet_id = "sheet-id"
        self.config.tracks_gid = 1
        self.config.projects_gid = 2
        self.config.save(update_fields=["sheet_id", "tracks_gid", "projects_gid"])

        with self.assertRaises(ScheduleSyncError):
            sync_schedule(self.config)

        self.config.refresh_from_db()
        self.assertIn("Unable to open the configured Google Sheet", self.config.sync_error)
