from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.event.models import CurrentProjectSchedule
from apps.event.services import ScheduleSyncError, ScheduleSyncStats


class SyncScheduleCommandTest(TestCase):
    def test_no_config_warns_and_skips(self):
        out = StringIO()
        call_command("sync_schedule", stdout=out)
        self.assertIn("No active schedule configuration found", out.getvalue())

    def test_not_due_skips_without_force(self):
        CurrentProjectSchedule.objects.create(name="Demo Day", auto_sync_enabled=False)
        out = StringIO()
        call_command("sync_schedule", stdout=out)
        self.assertIn("Auto-sync not due", out.getvalue())

    @patch("apps.event.management.commands.sync_schedule.sync_schedule")
    def test_force_syncs_and_prints_stats(self, mock_sync):
        config = CurrentProjectSchedule.objects.create(name="Demo Day")
        mock_sync.return_value = ScheduleSyncStats(
            sections_created=1,
            tracks_created=2,
            slots_created=3,
            unmatched_slots=4,
        )
        out = StringIO()

        call_command("sync_schedule", "--force", stdout=out)

        mock_sync.assert_called_once_with(config, sync_type="auto")
        output = out.getvalue()
        self.assertIn("1 sections", output)
        self.assertIn("2 tracks", output)
        self.assertIn("3 slots", output)
        self.assertIn("4 unmatched", output)

    @patch("apps.event.management.commands.sync_schedule.sync_schedule")
    def test_due_syncs_when_auto_enabled(self, mock_sync):
        config = CurrentProjectSchedule.objects.create(
            name="Demo Day",
            auto_sync_enabled=True,
            last_synced_at=None,
        )
        mock_sync.return_value = ScheduleSyncStats()
        out = StringIO()

        call_command("sync_schedule", stdout=out)

        mock_sync.assert_called_once_with(config, sync_type="auto")
        self.assertIn("Syncing 'Demo Day'", out.getvalue())

    @patch(
        "apps.event.management.commands.sync_schedule.sync_schedule",
        side_effect=ScheduleSyncError("sheet unreachable"),
    )
    def test_sync_failure_raises_command_error(self, _mock_sync):
        CurrentProjectSchedule.objects.create(name="Demo Day")
        with self.assertRaises(CommandError) as ctx:
            call_command("sync_schedule", "--force", stderr=StringIO())
        self.assertIn("Sync failed: 'Demo Day': sheet unreachable", str(ctx.exception))

    @patch("apps.event.management.commands.sync_schedule.sync_schedule")
    def test_cron_run_syncs_every_due_schedule_active_first(self, mock_sync):
        # Each schedule row (e.g. one per event year) has its own sheet and its
        # own auto-sync settings, so the cron run must not stop at the active one.
        # Create the active row FIRST so "active first" is proven by is_active,
        # not by the newest-first tie-breaker.
        active = CurrentProjectSchedule.objects.create(
            name="Innovate to Grow 2026",
            auto_sync_enabled=True,
            last_synced_at=None,
        )
        archived = CurrentProjectSchedule.objects.create(
            name="Innovate to Grow 2025",
            is_active=False,
            auto_sync_enabled=True,
            last_synced_at=None,
        )
        CurrentProjectSchedule.objects.create(name="Paused 2024", is_active=False, auto_sync_enabled=False)
        mock_sync.return_value = ScheduleSyncStats()
        out = StringIO()

        call_command("sync_schedule", stdout=out)

        self.assertEqual(
            [call.args[0] for call in mock_sync.call_args_list],
            [active, archived],
        )
        output = out.getvalue()
        self.assertIn("Syncing 'Innovate to Grow 2026'", output)
        self.assertIn("Syncing 'Innovate to Grow 2025'", output)
        self.assertIn("Auto-sync not due for 'Paused 2024'", output)

    @patch("apps.event.management.commands.sync_schedule.sync_schedule")
    def test_force_without_target_only_syncs_active_schedule(self, mock_sync):
        CurrentProjectSchedule.objects.create(name="Old", is_active=False, auto_sync_enabled=True)
        active = CurrentProjectSchedule.objects.create(name="Demo Day")
        mock_sync.return_value = ScheduleSyncStats()

        call_command("sync_schedule", "--force", stdout=StringIO())

        mock_sync.assert_called_once_with(active, sync_type="auto")

    @patch("apps.event.management.commands.sync_schedule.sync_schedule")
    def test_schedule_option_targets_a_non_active_schedule(self, mock_sync):
        CurrentProjectSchedule.objects.create(name="Demo Day")
        archived = CurrentProjectSchedule.objects.create(name="Innovate to Grow 2025", is_active=False)
        mock_sync.return_value = ScheduleSyncStats(sections_created=1)
        out = StringIO()

        call_command("sync_schedule", "--schedule", str(archived.pk), "--force", stdout=out)

        mock_sync.assert_called_once_with(archived, sync_type="auto")
        self.assertIn("Syncing 'Innovate to Grow 2025'", out.getvalue())

    @patch("apps.event.management.commands.sync_schedule.sync_schedule")
    def test_schedule_option_respects_due_check_without_force(self, mock_sync):
        archived = CurrentProjectSchedule.objects.create(
            name="Innovate to Grow 2025", is_active=False, auto_sync_enabled=False
        )
        out = StringIO()

        call_command("sync_schedule", "--schedule", str(archived.pk), stdout=out)

        mock_sync.assert_not_called()
        self.assertIn("Auto-sync not due for 'Innovate to Grow 2025'", out.getvalue())

    def test_schedule_option_unknown_id_raises(self):
        with self.assertRaises(CommandError) as ctx:
            call_command("sync_schedule", "--schedule", "00000000-0000-0000-0000-000000000000")
        self.assertIn("No CurrentProjectSchedule found", str(ctx.exception))

    def test_schedule_option_malformed_id_raises(self):
        with self.assertRaises(CommandError) as ctx:
            call_command("sync_schedule", "--schedule", "not-a-uuid")
        self.assertIn("No CurrentProjectSchedule found", str(ctx.exception))

    @patch("apps.event.management.commands.sync_schedule.sync_schedule")
    def test_one_failure_does_not_block_other_schedules(self, mock_sync):
        active = CurrentProjectSchedule.objects.create(name="2026", auto_sync_enabled=True)
        archived = CurrentProjectSchedule.objects.create(name="2025", is_active=False, auto_sync_enabled=True)

        def _sync(config, sync_type=""):
            if config == active:
                raise ScheduleSyncError("sheet unreachable")
            return ScheduleSyncStats()

        mock_sync.side_effect = _sync
        err = StringIO()

        with self.assertRaises(CommandError) as ctx:
            call_command("sync_schedule", stdout=StringIO(), stderr=err)

        self.assertEqual({call.args[0] for call in mock_sync.call_args_list}, {active, archived})
        self.assertIn("'2026': sheet unreachable", str(ctx.exception))
        self.assertIn("Sync failed for '2026'", err.getvalue())
