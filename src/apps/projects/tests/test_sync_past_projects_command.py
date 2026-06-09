from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.projects.models import PastProjectsSheetConfig
from apps.projects.services.sheet_sync import PastProjectSyncStats, SheetSyncError


class SyncPastProjectsCommandTest(TestCase):
    def test_no_config_warns_and_skips(self):
        out = StringIO()
        call_command("sync_past_projects", stdout=out)
        self.assertIn("No active past-projects sheet configuration", out.getvalue())

    def test_not_due_skips_without_force(self):
        PastProjectsSheetConfig.objects.create(name="Prod", is_active=True, auto_sync_enabled=False)
        out = StringIO()
        with patch("apps.projects.management.commands.sync_past_projects.sync_past_projects") as mock_sync:
            call_command("sync_past_projects", stdout=out)
        mock_sync.assert_not_called()
        self.assertIn("Auto-sync not due", out.getvalue())

    def test_force_syncs_and_prints_stats(self):
        config = PastProjectsSheetConfig.objects.create(name="Prod", is_active=True, auto_sync_enabled=False)
        out = StringIO()
        with patch(
            "apps.projects.management.commands.sync_past_projects.sync_past_projects",
            return_value=PastProjectSyncStats(
                rows_read=5,
                projects_created=2,
                projects_updated=1,
                projects_deleted=1,
                semesters_touched=1,
                rows_skipped=1,
            ),
        ) as mock_sync:
            call_command("sync_past_projects", "--force", stdout=out)
        mock_sync.assert_called_once_with(config, sync_type="auto")
        self.assertIn("Synced: 2 created, 1 updated, 1 deleted", out.getvalue())
        self.assertIn("1 rows skipped of 5 read", out.getvalue())

    def test_due_syncs_when_auto_enabled(self):
        config = PastProjectsSheetConfig.objects.create(
            name="Prod", is_active=True, auto_sync_enabled=True, last_synced_at=None
        )
        out = StringIO()
        with patch(
            "apps.projects.management.commands.sync_past_projects.sync_past_projects",
            return_value=PastProjectSyncStats(),
        ) as mock_sync:
            call_command("sync_past_projects", stdout=out)
        mock_sync.assert_called_once_with(config, sync_type="auto")

    def test_sync_failure_raises_command_error(self):
        PastProjectsSheetConfig.objects.create(name="Prod", is_active=True, auto_sync_enabled=True)
        with patch(
            "apps.projects.management.commands.sync_past_projects.sync_past_projects",
            side_effect=SheetSyncError("kaboom"),
        ):
            with self.assertRaises(CommandError) as ctx:
                call_command("sync_past_projects", "--force")
        self.assertIn("Sync failed: kaboom", str(ctx.exception))
