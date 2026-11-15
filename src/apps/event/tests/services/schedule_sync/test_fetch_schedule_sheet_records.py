from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.event.models import CurrentProjectSchedule
from apps.event.services.schedule_sync.shared import ScheduleSyncError
from apps.event.services.schedule_sync.sheets import (
    fetch_schedule_sheet_records,
)


class FetchScheduleSheetRecordsTest(TestCase):
    def _configure(self):
        config = CurrentProjectSchedule.objects.create(
            name="Demo Day",
            sheet_id="sheet-id",
            tracks_gid=1,
            projects_gid=2,
        )
        return config

    def test_unconfigured_source_raises(self):
        config = CurrentProjectSchedule.objects.create(name="Empty")
        with self.assertRaises(ScheduleSyncError) as ctx:
            fetch_schedule_sheet_records(config)
        self.assertIn("not fully configured", str(ctx.exception))

    @patch("apps.event.services.schedule_sync.sheets.GoogleCredentialConfig.load")
    def test_gid_zero_is_a_valid_worksheet_id(self, mock_load):
        # The first tab of every spreadsheet has gid 0; it must not read as "unconfigured".
        config = CurrentProjectSchedule.objects.create(
            name="Demo Day", sheet_id="sheet-id", tracks_gid=0, projects_gid=2
        )
        mock_load.return_value = MagicMock(
            is_configured=True,
            get_credentials_info=MagicMock(return_value={"client_email": "x@example.com"}),
        )
        tracks_ws = MagicMock(id=0)
        tracks_ws.get_all_records.return_value = [{"Track": 1}]
        projects_ws = MagicMock(id=2)
        projects_ws.get_all_records.return_value = [{"Team#": "CAP-1"}]
        spreadsheet = MagicMock(worksheets=MagicMock(return_value=[tracks_ws, projects_ws]))
        client = MagicMock()
        client.open_by_key.return_value = spreadsheet
        with patch("gspread.service_account_from_dict", return_value=client):
            tracks, projects = fetch_schedule_sheet_records(config)
        self.assertEqual(tracks, [{"Track": 1}])
        self.assertEqual(projects, [{"Team#": "CAP-1"}])
        # One metadata call serves both worksheet lookups.
        spreadsheet.worksheets.assert_called_once()

    def test_none_source_raises(self):
        with self.assertRaises(ScheduleSyncError) as ctx:
            fetch_schedule_sheet_records(None)
        self.assertIn("not fully configured", str(ctx.exception))

    @patch("apps.event.services.schedule_sync.sheets.GoogleCredentialConfig.load")
    def test_reads_the_passed_schedules_own_sheet_not_the_active_one(self, mock_load):
        # Regression: the fetch used to resolve CurrentProjectSchedule.load()
        # internally, so syncing a non-active (e.g. previous-year) schedule
        # silently pulled the ACTIVE schedule's sheet into it.
        self._configure()  # active, sheet-id / gids 1,2
        archived = CurrentProjectSchedule.objects.create(
            name="Innovate to Grow 2025",
            is_active=False,
            sheet_id="archived-sheet-id",
            tracks_gid=11,
            projects_gid=22,
        )
        mock_load.return_value = MagicMock(
            is_configured=True,
            get_credentials_info=MagicMock(return_value={"client_email": "x@example.com"}),
        )
        tracks_ws = MagicMock(id=11)
        tracks_ws.get_all_records.return_value = [{"Track": "archived"}]
        projects_ws = MagicMock(id=22)
        projects_ws.get_all_records.return_value = [{"Team#": "OLD-1"}]
        spreadsheet = MagicMock(worksheets=MagicMock(return_value=[tracks_ws, projects_ws]))
        client = MagicMock()
        client.open_by_key.return_value = spreadsheet
        with patch("gspread.service_account_from_dict", return_value=client):
            tracks, projects = fetch_schedule_sheet_records(archived)
        client.open_by_key.assert_called_once_with("archived-sheet-id")
        self.assertEqual(tracks, [{"Track": "archived"}])
        self.assertEqual(projects, [{"Team#": "OLD-1"}])

    @patch("apps.event.services.schedule_sync.sheets.GoogleCredentialConfig.load")
    def test_unconfigured_credentials_raises(self, mock_load):
        config = self._configure()
        mock_load.return_value = MagicMock(is_configured=False)
        with self.assertRaises(ScheduleSyncError) as ctx:
            fetch_schedule_sheet_records(config)
        self.assertIn("No active Google service account", str(ctx.exception))

    @patch("apps.event.services.schedule_sync.sheets.GoogleCredentialConfig.load")
    def test_missing_tracks_worksheet_raises(self, mock_load):
        config = self._configure()
        mock_load.return_value = MagicMock(
            is_configured=True,
            get_credentials_info=MagicMock(return_value={"client_email": "x@example.com"}),
        )
        # tracks gid 1 not present, projects gid 2 present.
        spreadsheet = MagicMock(worksheets=MagicMock(return_value=[MagicMock(id=2)]))
        client = MagicMock()
        client.open_by_key.return_value = spreadsheet
        with patch("gspread.service_account_from_dict", return_value=client):
            with self.assertRaises(ScheduleSyncError) as ctx:
                fetch_schedule_sheet_records(config)
        self.assertIn("tracks worksheet not found", str(ctx.exception))

    @patch("apps.event.services.schedule_sync.sheets.GoogleCredentialConfig.load")
    def test_missing_projects_worksheet_raises(self, mock_load):
        config = self._configure()
        mock_load.return_value = MagicMock(
            is_configured=True,
            get_credentials_info=MagicMock(return_value={"client_email": "x@example.com"}),
        )
        spreadsheet = MagicMock(worksheets=MagicMock(return_value=[MagicMock(id=1)]))
        client = MagicMock()
        client.open_by_key.return_value = spreadsheet
        with patch("gspread.service_account_from_dict", return_value=client):
            with self.assertRaises(ScheduleSyncError) as ctx:
                fetch_schedule_sheet_records(config)
        self.assertIn("projects worksheet not found", str(ctx.exception))

    @patch("apps.event.services.schedule_sync.sheets.GoogleCredentialConfig.load")
    def test_returns_records_for_both_worksheets(self, mock_load):
        config = self._configure()
        mock_load.return_value = MagicMock(
            is_configured=True,
            get_credentials_info=MagicMock(return_value={"client_email": "x@example.com"}),
        )
        tracks_ws = MagicMock(id=1)
        tracks_ws.get_all_records.return_value = [{"Track": 1}]
        projects_ws = MagicMock(id=2)
        projects_ws.get_all_records.return_value = [{"Team#": "CAP-1"}]
        spreadsheet = MagicMock(worksheets=MagicMock(return_value=[tracks_ws, projects_ws]))
        client = MagicMock()
        client.open_by_key.return_value = spreadsheet
        with patch("gspread.service_account_from_dict", return_value=client):
            tracks, projects = fetch_schedule_sheet_records(config)
        self.assertEqual(tracks, [{"Track": 1}])
        self.assertEqual(projects, [{"Team#": "CAP-1"}])

    @patch("apps.event.services.schedule_sync.sheets.GoogleCredentialConfig.load")
    def test_open_failure_raises_schedule_sync_error(self, mock_load):
        # When gspread cannot open the configured sheet, the error is wrapped.
        config = self._configure()
        mock_load.return_value = MagicMock(
            is_configured=True,
            get_credentials_info=MagicMock(return_value={"client_email": "x@example.com"}),
        )
        client = MagicMock()
        client.open_by_key.side_effect = RuntimeError("boom: sheet unreachable")
        with patch("gspread.service_account_from_dict", return_value=client):
            with self.assertRaises(ScheduleSyncError) as ctx:
                fetch_schedule_sheet_records(config)
        self.assertIn("Unable to open the configured Google Sheet", str(ctx.exception))
        self.assertIn("boom: sheet unreachable", str(ctx.exception))

    @patch("apps.event.services.schedule_sync.sheets.GoogleCredentialConfig.load")
    def test_get_all_records_failure_raises_schedule_sync_error(self, mock_load):
        # When reading worksheet records fails, the error is wrapped.
        config = self._configure()
        mock_load.return_value = MagicMock(
            is_configured=True,
            get_credentials_info=MagicMock(return_value={"client_email": "x@example.com"}),
        )
        tracks_ws = MagicMock(id=1)
        tracks_ws.get_all_records.side_effect = RuntimeError("read failed")
        projects_ws = MagicMock(id=2)
        spreadsheet = MagicMock(worksheets=MagicMock(return_value=[tracks_ws, projects_ws]))
        client = MagicMock()
        client.open_by_key.return_value = spreadsheet
        with patch("gspread.service_account_from_dict", return_value=client):
            with self.assertRaises(ScheduleSyncError) as ctx:
                fetch_schedule_sheet_records(config)
        self.assertIn("Unable to read schedule worksheet records", str(ctx.exception))
        self.assertIn("read failed", str(ctx.exception))
