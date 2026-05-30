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
            call_command("sync_schedule", "--force")
        self.assertIn("Sync failed: sheet unreachable", str(ctx.exception))
