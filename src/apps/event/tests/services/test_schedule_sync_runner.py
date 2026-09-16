from unittest.mock import patch

from django.test import TestCase

from apps.event.models import (
    CurrentProjectSchedule,
    EventScheduleSlot,
    ScheduleSyncLog,
)
from apps.event.services import ScheduleSyncError, sync_schedule


class SyncScheduleRunnerTest(TestCase):
    def setUp(self):
        self.config = CurrentProjectSchedule.objects.create(name="Demo Day")

    def test_empty_parsed_data_raises_schedule_sync_error(self):
        with self.assertRaises(ScheduleSyncError) as ctx:
            sync_schedule(self.config, tracks_records=[], projects_records=[])
        self.assertIn("does not contain any schedule tracks or slots", str(ctx.exception))

        self.config.refresh_from_db()
        self.assertIn("does not contain any", self.config.sync_error)
        log = ScheduleSyncLog.objects.filter(config=self.config).last()
        self.assertEqual(log.status, ScheduleSyncLog.Status.FAILED)

    @patch("apps.event.services.schedule_sync.runner.fetch_schedule_sheet_records")
    def test_fetches_the_synced_schedules_own_sheet_even_when_not_active(self, mock_fetch):
        # Regression: the runner used to call the fetch helper with no argument
        # and the helper resolved the ACTIVE schedule, so syncing a previous
        # year's row pulled the active year's sheet into it.
        # Give the ACTIVE schedule real data first so "untouched" means something.
        sync_schedule(
            self.config,
            tracks_records=[{"Track": 1, "Class": "CAP", "Room": "Active Hall"}],
            projects_records=[
                {"Track": 1, "Order": 1, "Class": "CAP", "Team#": "NEW-1", "Project Title": "Alpha 2026"}
            ],
        )
        self.config.refresh_from_db()
        active_synced_at = self.config.last_synced_at
        self.assertIsNotNone(active_synced_at)

        archived = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2025", is_active=False)
        mock_fetch.return_value = (
            [{"Track": 1, "Class": "CAP", "Room": "Granite"}],
            [{"Track": 1, "Order": 1, "Class": "CAP", "Team#": "OLD-1", "Project Title": "Alpha 2025"}],
        )

        stats = sync_schedule(archived, sync_type="manual")

        mock_fetch.assert_called_once_with(archived)
        self.assertEqual(stats.slots_created, 1)
        self.assertTrue(EventScheduleSlot.objects.filter(track__section__config=archived, team_number="OLD-1").exists())
        # The active schedule keeps its own rows and sync timestamp.
        active_slots = EventScheduleSlot.objects.filter(track__section__config=self.config)
        self.assertEqual(list(active_slots.values_list("team_number", flat=True)), ["NEW-1"])
        self.assertEqual(active_slots.first().track.room, "Active Hall")
        self.config.refresh_from_db()
        self.assertEqual(self.config.last_synced_at, active_synced_at)
        archived.refresh_from_db()
        self.assertIsNotNone(archived.last_synced_at)

    def test_syncing_an_archived_schedule_leaves_the_current_projects_cache_alone(self):
        from django.core.cache import cache

        archived = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2025", is_active=False)
        tracks = [{"Track": 1, "Class": "CAP", "Room": "Granite"}]
        projects = [{"Track": 1, "Order": 1, "Class": "CAP", "Team#": "OLD-1", "Project Title": "Alpha"}]
        cache.set("event:current-projects", {"cached": True}, timeout=300)

        sync_schedule(archived, tracks_records=tracks, projects_records=projects)
        self.assertEqual(cache.get("event:current-projects"), {"cached": True})

        sync_schedule(self.config, tracks_records=tracks, projects_records=projects)
        self.assertIsNone(cache.get("event:current-projects"))

    def test_generic_exception_wrapped_in_schedule_sync_error(self):
        tracks = [{"Track": 1, "Class": "CAP", "Room": "Granite"}]
        projects = [{"Track": 1, "Order": 1, "Class": "CAP", "Team#": "CAP-1", "Project Title": "Alpha"}]

        with patch(
            "apps.event.services.schedule_sync.runner.create_sections",
            side_effect=RuntimeError("db gone"),
        ):
            with self.assertRaises(ScheduleSyncError) as ctx:
                sync_schedule(self.config, tracks_records=tracks, projects_records=projects)

        self.assertIn("db gone", str(ctx.exception))
        log = ScheduleSyncLog.objects.filter(config=self.config).last()
        self.assertEqual(log.status, ScheduleSyncLog.Status.FAILED)

    def test_failure_skips_log_for_unsaved_config(self):
        unsaved = CurrentProjectSchedule()
        with self.assertRaises(ScheduleSyncError):
            sync_schedule(unsaved, tracks_records=[], projects_records=[])
        # No log written for a config that was never persisted.
        self.assertFalse(ScheduleSyncLog.objects.filter(config__isnull=True).exists())

    def test_slot_for_unknown_track_is_skipped(self):
        # Track 1 defined; slot references track 9 (no track) -> create_slots `continue`.
        tracks = [{"Track": 1, "Class": "CAP", "Room": "Granite"}]
        projects = [
            {"Track": 1, "Order": 1, "Class": "CAP", "Team#": "CAP-1", "Project Title": "Alpha"},
            {"Track": 9, "Order": 1, "Class": "CAP", "Team#": "CAP-9", "Project Title": "Orphan"},
        ]
        stats = sync_schedule(self.config, tracks_records=tracks, projects_records=projects)

        self.assertEqual(stats.slots_created, 1)
        self.assertFalse(
            EventScheduleSlot.objects.filter(track__section__config=self.config, team_number="CAP-9").exists()
        )

    def test_unmatched_slot_counted_when_project_lookup_misses(self):
        # A slot whose class_code does not normalize to the project's section
        # makes current_projects lookup miss -> unmatched_slots increments.
        tracks = [{"Track": 1, "Class": "CAP", "Room": "Granite"}]
        projects = [
            {
                "Track": 1,
                "Order": 1,
                "Class": "Break",
                "Team#": "X-1",
                "Project Title": "Mystery",
            }
        ]
        stats = sync_schedule(self.config, tracks_records=tracks, projects_records=projects)

        self.assertEqual(stats.slots_created, 1)
        self.assertEqual(stats.unmatched_slots, 1)
        slot = EventScheduleSlot.objects.get(track__section__config=self.config, team_number="X-1")
        self.assertIsNone(slot.project)
