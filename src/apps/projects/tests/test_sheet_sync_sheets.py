from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.core.models import GoogleCredentialConfig
from apps.projects.models import PastProjectsSheetConfig
from apps.projects.services.sheet_sync import SheetSyncError, fetch_past_project_records

_CREDS = {
    "type": "service_account",
    "project_id": "demo",
    "private_key": "KEY",
    "client_email": "svc@demo.iam.gserviceaccount.com",
    "token_uri": "https://oauth2.googleapis.com/token",
}


class FetchPastProjectRecordsTest(TestCase):
    def _active_config(self):
        return PastProjectsSheetConfig.objects.create(
            name="Prod", is_active=True, sheet_id="SHEET123", worksheet_name="Past-Projects-WEB-LIVE"
        )

    def _active_creds(self):
        return GoogleCredentialConfig.objects.create(name="G", is_active=True, credentials_json=_CREDS)

    def test_not_configured_raises(self):
        # No active config at all.
        with self.assertRaises(SheetSyncError) as ctx:
            fetch_past_project_records()
        self.assertIn("not fully configured", str(ctx.exception))

    def test_missing_sheet_id_raises(self):
        PastProjectsSheetConfig.objects.create(name="Prod", is_active=True, sheet_id="")
        with self.assertRaises(SheetSyncError):
            fetch_past_project_records()

    def test_no_google_creds_raises(self):
        self._active_config()
        # No active GoogleCredentialConfig → load() returns an unconfigured instance.
        with self.assertRaises(SheetSyncError) as ctx:
            fetch_past_project_records()
        self.assertIn("No active Google service account", str(ctx.exception))

    def test_open_failure_wrapped(self):
        self._active_config()
        self._active_creds()
        with patch("gspread.service_account_from_dict", side_effect=RuntimeError("boom")):
            with self.assertRaises(SheetSyncError) as ctx:
                fetch_past_project_records()
        self.assertIn("Unable to open", str(ctx.exception))

    def test_read_failure_wrapped(self):
        self._active_config()
        self._active_creds()
        worksheet = MagicMock()
        worksheet.get_all_records.side_effect = RuntimeError("read kaboom")
        spreadsheet = MagicMock()
        spreadsheet.worksheet.return_value = worksheet
        client = MagicMock()
        client.open_by_key.return_value = spreadsheet
        with patch("gspread.service_account_from_dict", return_value=client):
            with self.assertRaises(SheetSyncError) as ctx:
                fetch_past_project_records()
        self.assertIn("Unable to read", str(ctx.exception))

    def test_success_returns_records(self):
        self._active_config()
        self._active_creds()
        rows = [{"Year-Semester": "2024-2 Fall", "Project Title": "X"}]
        worksheet = MagicMock()
        worksheet.get_all_records.return_value = rows
        spreadsheet = MagicMock()
        spreadsheet.worksheet.return_value = worksheet
        client = MagicMock()
        client.open_by_key.return_value = spreadsheet
        with patch("gspread.service_account_from_dict", return_value=client):
            result = fetch_past_project_records()
        self.assertEqual(result, rows)
        client.open_by_key.assert_called_once_with("SHEET123")
        spreadsheet.worksheet.assert_called_once_with("Past-Projects-WEB-LIVE")
