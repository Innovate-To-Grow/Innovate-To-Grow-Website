from unittest.mock import patch

from django.test import TestCase

from event.models import (
    CurrentProjectSchedule,
    EventAgendaItem,
    EventScheduleSection,
    EventScheduleSlot,
    EventScheduleTrack,
)
from event.services import ScheduleSyncError, sync_event_schedule
from event.tests.helpers import make_event
from projects.models import Project, Semester


def _tracks_records():
    return [
        {"Track": 1, "Room": "Granite", "Class": "CAP", "Topic": "FoodTech"},
        {"Track": 2, "Room": "Cypress", "Class": "CEE", "Topic": "Environment"},
        {"Track": 3, "Room": "COB 105", "Class": "CSE", "Topic": "Tim Berners-Lee"},
    ]


def _projects_records():
    return [
        {
            "Track": 1,
            "Order": 1,
            "Year-Semester": "2025-1 Spring",
            "Class": "CAP",
            "Team#": "CAP-101",
            "Team Name": "Alpha",
            "Project Title": "Smart Farm",
            "Organization": "Agri Corp",
            "Industry": "Ag",
            "Abstract": "A smart farming project.",
            "Student Names": "Ada, Ben",
            "Name Title": "Mentor - Lead",
        },
        {
            "Track": 1,
            "Order": 2,
            "Year-Semester": "2025-1 Spring",
            "Class": "CAP",
            "Project Title": "Break",
        },
        {
            "Track": 3,
            "Order": 1,
            "Year-Semester": "2025-1 Spring",
            "Class": "CSE",
            "Team#": "CSE-201",
            "Team Name": "Delta",
            "Project Title": "Campus Navigator",
            "Organization": "UC Merced",
            "Industry": "Education",
            "Abstract": "A route finder for students.",
            "Student Names": "Carol, Dan",
            "Name Title": "Faculty - Sponsor",
        },
        {
            "Track": 2,
            "Order": 1,
            "Year-Semester": "2025-1 Spring",
            "Class": "CEE",
            "Team#": "CEE-999",
            "Team Name": "River Works",
            "Project Title": "Flood Mapper",
            "Organization": "County Office",
            "Industry": "Government",
        },
    ]


class ScheduleSyncServiceTest(TestCase):
    def setUp(self):
        self.semester = Semester.objects.create(year=2025, season=1, is_published=True)
        self.event = make_event(is_live=True)
        self.config = CurrentProjectSchedule.objects.create()
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
        stats = sync_event_schedule(
            self.event,
            tracks_records=_tracks_records(),
            projects_records=_projects_records(),
        )

        self.config.refresh_from_db()
        self.assertEqual(stats.sections_created, 3)
        self.assertEqual(stats.tracks_created, 3)
        self.assertEqual(stats.slots_created, 3)
        self.assertEqual(stats.unmatched_slots, 1)
        self.assertIsNotNone(self.config.last_synced_at)
        self.assertEqual(self.config.sync_error, "")
        self.assertEqual(EventScheduleSection.objects.filter(event=self.event).count(), 3)
        self.assertEqual(EventScheduleTrack.objects.count(), 3)
        self.assertEqual(EventScheduleSlot.objects.count(), 3)
        self.assertEqual(EventAgendaItem.objects.filter(event=self.event).count(), 4)

        cap_slot = EventScheduleSlot.objects.get(team_number="CAP-101")
        self.assertEqual(cap_slot.project, self.cap_project)
        self.assertEqual(cap_slot.display_text, "CAP-101")

        # Break rows are skipped — not imported as slots
        self.assertFalse(EventScheduleSlot.objects.filter(is_break=True).exists())

        unmatched_slot = EventScheduleSlot.objects.get(team_number="CEE-999")
        self.assertIsNone(unmatched_slot.project)

    def test_sync_replaces_existing_schedule_only_for_target_event(self):
        other_event = make_event(name="Other Event")
        other_section = EventScheduleSection.objects.create(event=other_event, code="CAP", label="Other")
        other_track = EventScheduleTrack.objects.create(section=other_section, track_number=1)
        EventScheduleSlot.objects.create(track=other_track, slot_order=1, display_text="OTHER-1")

        sync_event_schedule(
            self.event,
            tracks_records=_tracks_records(),
            projects_records=_projects_records(),
        )
        sync_event_schedule(
            self.event,
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

        self.assertEqual(EventScheduleSection.objects.filter(event=self.event).count(), 1)
        self.assertEqual(EventScheduleSlot.objects.filter(track__section__event=self.event).count(), 1)
        self.assertEqual(EventScheduleSlot.objects.filter(track__section__event=other_event).count(), 1)

    def test_sync_raises_when_no_config(self):
        self.config.delete()
        with self.assertRaises(ScheduleSyncError):
            sync_event_schedule(self.event)

    @patch("event.services.schedule_sync.GoogleCredentialConfig.load")
    @patch("event.services.schedule_sync.gspread.service_account_from_dict")
    def test_sync_surfaces_sheet_open_errors(self, mock_service_account, mock_load_credentials):
        mock_service_account.side_effect = RuntimeError("boom")
        mock_load_credentials.return_value.is_configured = True
        mock_load_credentials.return_value.get_credentials_info.return_value = {"client_email": "test@example.com"}
        self.config.sheet_id = "sheet-id"
        self.config.tracks_gid = 1
        self.config.projects_gid = 2
        self.config.save(update_fields=["sheet_id", "tracks_gid", "projects_gid"])

        with self.assertRaises(ScheduleSyncError):
            sync_event_schedule(self.event)

        self.config.refresh_from_db()
        self.assertIn("Unable to open the configured Google Sheet", self.config.sync_error)
