from unittest.mock import patch

from django.test import TestCase

from apps.event.models import (
    CurrentProject,
    CurrentProjectSchedule,
    EventAgendaItem,
    EventScheduleSection,
    EventScheduleSlot,
    EventScheduleTrack,
)
from apps.event.services import ScheduleSyncError, ScheduleSyncStats, sync_schedule
from apps.event.tests.helpers import sample_projects_records, sample_tracks_records


class ScheduleSyncServiceTest(TestCase):
    def setUp(self):
        self.config = CurrentProjectSchedule.objects.create(name="Demo Day")

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
        self.assertIsNotNone(cap_slot.project)
        self.assertIsInstance(cap_slot.project, CurrentProject)
        self.assertEqual(cap_slot.project.project_title, "Smart Farm")
        self.assertEqual(cap_slot.display_text, "CAP-101")

        break_slot = EventScheduleSlot.objects.get(is_break=True)
        self.assertEqual(break_slot.display_text, "Break")

        cee_slot = EventScheduleSlot.objects.get(team_number="CEE-999")
        self.assertIsNotNone(cee_slot.project)

        self.assertEqual(CurrentProject.objects.filter(schedule=self.config).count(), 3)

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

    def test_first_sync_seeds_the_default_agenda(self):
        stats = sync_schedule(
            self.config,
            tracks_records=sample_tracks_records(),
            projects_records=sample_projects_records(),
        )

        self.assertEqual(stats.agenda_items_created, 4)
        expo = EventAgendaItem.objects.filter(config=self.config, section_type=EventAgendaItem.SectionType.EXPO)
        self.assertEqual(
            list(expo.order_by("display_order").values_list("time_label", "title")),
            [("9:00", "Registration and Coffee"), ("10:00", "Expo - Posters - Demos - Lunch")],
        )

    def test_later_syncs_keep_agenda_items_edited_in_admin(self):
        sync_schedule(self.config, tracks_records=sample_tracks_records(), projects_records=sample_projects_records())
        edited = EventAgendaItem.objects.get(config=self.config, title="Registration and Coffee")
        edited.title = "Check-in and Breakfast"
        edited.location = "Student Union"
        edited.save()
        EventAgendaItem.objects.filter(config=self.config, title="Reception").delete()

        stats = sync_schedule(
            self.config, tracks_records=sample_tracks_records(), projects_records=sample_projects_records()
        )

        self.assertEqual(stats.agenda_items_created, 0)
        self.assertEqual(EventAgendaItem.objects.filter(config=self.config).count(), 3)
        edited.refresh_from_db()
        self.assertEqual((edited.title, edited.location), ("Check-in and Breakfast", "Student Union"))

    def test_an_agenda_emptied_on_purpose_stays_empty(self):
        sync_schedule(self.config, tracks_records=sample_tracks_records(), projects_records=sample_projects_records())
        EventAgendaItem.objects.filter(config=self.config).delete()

        sync_schedule(self.config, tracks_records=sample_tracks_records(), projects_records=sample_projects_records())

        self.assertFalse(EventAgendaItem.objects.filter(config=self.config).exists())

    def test_first_sync_does_not_add_defaults_next_to_agenda_items_entered_beforehand(self):
        EventAgendaItem.objects.create(
            config=self.config,
            section_type=EventAgendaItem.SectionType.EXPO,
            time_label="8:30",
            title="Doors open",
            location="Courtyard",
            display_order=0,
        )

        stats = sync_schedule(
            self.config, tracks_records=sample_tracks_records(), projects_records=sample_projects_records()
        )

        self.assertEqual(stats.agenda_items_created, 0)
        self.assertEqual(
            list(EventAgendaItem.objects.filter(config=self.config).values_list("title", flat=True)), ["Doors open"]
        )

    def test_agenda_seeding_ignores_a_stale_config_copy(self):
        sync_schedule(self.config, tracks_records=sample_tracks_records(), projects_records=sample_projects_records())
        EventAgendaItem.objects.filter(config=self.config).delete()
        stale = CurrentProjectSchedule(pk=self.config.pk)  # last_synced_at unset in memory, set in the database

        from apps.event.services.schedule_sync.writing import create_agenda_items

        create_agenda_items(stale, ScheduleSyncStats())

        self.assertFalse(EventAgendaItem.objects.filter(config=self.config).exists())

    def test_rows_with_blank_track_and_order_are_non_presenting(self):
        tracks = [{"Track": 1, "Room": "Granite", "Class": "CAP", "Topic": "FoodTech"}]
        projects = [
            {"Track": 1, "Order": 1, "Class": "CAP", "Team#": "CAP-101", "Team Name": "Alpha", "Project Title": "A"},
            {"Track": "", "Order": "", "Class": "CAP", "Team#": "CAP-201", "Team Name": "Beta", "Project Title": "B"},
            {"Track": 1, "Order": "", "Class": "CAP", "Team#": "CAP-301", "Team Name": "Gamma", "Project Title": "C"},
            {
                "Track": 1,
                "Order": "TBD",
                "Class": "CAP",
                "Team#": "CAP-401",
                "Team Name": "Delta",
                "Project Title": "D",
            },
        ]

        stats = sync_schedule(self.config, tracks_records=tracks, projects_records=projects)

        self.assertEqual(stats.slots_created, 1)
        self.assertTrue(CurrentProject.objects.get(team_number="CAP-101").is_presenting)
        self.assertFalse(CurrentProject.objects.get(team_number="CAP-201").is_presenting)
        # Half-filled / non-numeric rows are malformed: skipped, not demoted.
        self.assertFalse(CurrentProject.objects.filter(team_number__in=["CAP-301", "CAP-401"]).exists())

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
