from unittest.mock import patch

from django.test import TestCase

from event.models import (
    CurrentProjectSchedule,
    EventAgendaItem,
    EventScheduleSection,
    EventScheduleSlot,
    EventScheduleTrack,
)
from event.services import ScheduleSyncError, sync_schedule
from event.tests.helpers import sample_projects_records, sample_tracks_records
from projects.models import Project, Semester


class ScheduleSyncServiceTest(TestCase):
    def setUp(self):
        self.semester = Semester.objects.create(year=2025, season=1, is_published=True)
        self.config = CurrentProjectSchedule.objects.create(name="Demo Day")
        self.cap_project = Project.objects.create(
            semester=self.semester,
            class_code="CAP",
            team_number="CAP-101",
            team_name="Alpha",
            project_title="Smart Farm",
        )
        self.cse_project = Project.objects.create(
            semester=self.semester,
            class_code="CSE",
            team_number="CSE-201",
            team_name="Delta",
            project_title="Campus Navigator",
        )

    def test_sync_creates_sections_tracks_slots_and_agenda_items(self):
        stats = sync_schedule(
            self.config,
            tracks_records=sample_tracks_records(),
            projects_records=sample_projects_records(),
        )

        self.config.refresh_from_db()
        self.assertEqual(stats.sections_created, 3)
        self.assertEqual(stats.tracks_created, 3)
        self.assertEqual(stats.slots_created, 4)
        self.assertEqual(stats.break_slots, 1)
        self.assertEqual(stats.unmatched_slots, 0)
        self.assertIsNotNone(self.config.last_synced_at)
        self.assertEqual(self.config.sync_error, "")
        self.assertEqual(EventScheduleSection.objects.filter(config=self.config).count(), 3)
        self.assertEqual(EventScheduleTrack.objects.count(), 3)
        self.assertEqual(EventScheduleSlot.objects.count(), 4)
        self.assertEqual(EventAgendaItem.objects.filter(config=self.config).count(), 4)

        cap_slot = EventScheduleSlot.objects.get(team_number="CAP-101")
        self.assertEqual(cap_slot.project, self.cap_project)
        self.assertEqual(cap_slot.display_text, "CAP-101")

        break_slot = EventScheduleSlot.objects.get(is_break=True)
        self.assertEqual(break_slot.display_text, "Break")

        cee_slot = EventScheduleSlot.objects.get(team_number="CEE-999")
        self.assertIsNotNone(cee_slot.project)

    def test_sync_replaces_existing_schedule(self):
        other_config = CurrentProjectSchedule.objects.create(name="Other")
        other_section = EventScheduleSection.objects.create(config=other_config, code="CAP", label="Other")
        other_track = EventScheduleTrack.objects.create(section=other_section, track_number=1)
        EventScheduleSlot.objects.create(track=other_track, slot_order=1, display_text="OTHER-1")

        sync_schedule(
            self.config,
            tracks_records=sample_tracks_records(),
            projects_records=sample_projects_records(),
        )
        sync_schedule(
            self.config,
            tracks_records=[{"Track": 1, "Room": "Granite", "Class": "CAP", "Topic": "FoodTech"}],
            projects_records=[
                {
                    "Track": 1,
                    "Order": 1,
                    "Year-Semester": "2025-1 Spring",
                    "Class": "CAP",
                    "Team#": "CAP-101",
                    "Team Name": "Alpha",
                    "Project Title": "Smart Farm",
                }
            ],
        )

        self.assertEqual(EventScheduleSection.objects.filter(config=self.config).count(), 1)
        self.assertEqual(EventScheduleSlot.objects.filter(track__section__config=self.config).count(), 1)
        self.assertEqual(EventScheduleSlot.objects.filter(track__section__config=other_config).count(), 1)

    def test_sync_raises_when_no_config(self):
        empty_config = CurrentProjectSchedule()
        with self.assertRaises(ScheduleSyncError):
            sync_schedule(empty_config)

    @patch("event.services.schedule_sync.GoogleCredentialConfig.load")
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
