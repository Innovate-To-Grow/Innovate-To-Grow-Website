from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.event.services.registration_sheet_sync import RegistrationSyncError
from apps.event.services.registration_sheet_sync.worksheet.sheets import (
    _get_worksheet,
    _get_worksheet_by_gid,
    ensure_registration_id_protected,
    registration_ids_from_values,
)
from apps.event.tests.helpers import make_event


class SheetsHelperTest(TestCase):
    def setUp(self):
        self.event = make_event(name="Sheets Event", registration_sheet_id="sheet-id")

    def test_get_worksheet_by_gid_returns_match(self):
        ws_a = MagicMock(id=10)
        ws_b = MagicMock(id=20)
        spreadsheet = MagicMock(worksheets=MagicMock(return_value=[ws_a, ws_b]))
        self.assertIs(_get_worksheet_by_gid(spreadsheet, 20), ws_b)

    def test_get_worksheet_by_gid_returns_none_when_missing(self):
        spreadsheet = MagicMock(worksheets=MagicMock(return_value=[MagicMock(id=1)]))
        self.assertIsNone(_get_worksheet_by_gid(spreadsheet, 999))

    @patch("apps.event.services.registration_sheet_sync.worksheet.sheets.GoogleCredentialConfig.load")
    def test_get_worksheet_unconfigured_raises(self, mock_load):
        mock_load.return_value = MagicMock(is_configured=False)
        with self.assertRaises(RegistrationSyncError):
            _get_worksheet(self.event)

    @patch("apps.event.services.registration_sheet_sync.worksheet.sheets.GoogleCredentialConfig.load")
    def test_get_worksheet_uses_sheet1_when_no_gid(self, mock_load):
        mock_load.return_value = MagicMock(
            is_configured=True,
            get_credentials_info=MagicMock(return_value={"client_email": "x@example.com"}),
        )
        sheet1 = MagicMock()
        client = MagicMock()
        client.open_by_key.return_value = MagicMock(sheet1=sheet1)
        with patch("gspread.service_account_from_dict", return_value=client):
            result = _get_worksheet(self.event)
        self.assertIs(result, sheet1)

    @patch("apps.event.services.registration_sheet_sync.worksheet.sheets.GoogleCredentialConfig.load")
    def test_get_worksheet_resolves_by_gid(self, mock_load):
        mock_load.return_value = MagicMock(
            is_configured=True,
            get_credentials_info=MagicMock(return_value={"client_email": "x@example.com"}),
        )
        self.event.registration_sheet_gid = 42
        self.event.save(update_fields=["registration_sheet_gid", "updated_at"])
        target = MagicMock(id=42)
        spreadsheet = MagicMock(worksheets=MagicMock(return_value=[target]))
        client = MagicMock()
        client.open_by_key.return_value = spreadsheet
        with patch("gspread.service_account_from_dict", return_value=client):
            result = _get_worksheet(self.event)
        self.assertIs(result, target)

    @patch("apps.event.services.registration_sheet_sync.worksheet.sheets.GoogleCredentialConfig.load")
    def test_get_worksheet_missing_gid_raises(self, mock_load):
        mock_load.return_value = MagicMock(
            is_configured=True,
            get_credentials_info=MagicMock(return_value={"client_email": "x@example.com"}),
        )
        self.event.registration_sheet_gid = 7
        self.event.save(update_fields=["registration_sheet_gid", "updated_at"])
        spreadsheet = MagicMock(worksheets=MagicMock(return_value=[MagicMock(id=1)]))
        client = MagicMock()
        client.open_by_key.return_value = spreadsheet
        with patch("gspread.service_account_from_dict", return_value=client):
            with self.assertRaises(RegistrationSyncError) as ctx:
                _get_worksheet(self.event)
        self.assertIn("GID not found", str(ctx.exception))

    def test_header_only_legacy_sheet_is_rejected_for_append(self):
        with self.assertRaisesMessage(RegistrationSyncError, "no valid final Registration ID"):
            registration_ids_from_values([["Order", "First Name"]])

    def test_drifted_header_is_rejected_for_append(self):
        expected = ["Order", "First Name", "Registration ID"]
        drifted = [["Order", "Unexpected Question", "Registration ID"]]
        with self.assertRaisesMessage(RegistrationSyncError, "no longer match"):
            registration_ids_from_values(drifted, expected_header=expected)

    def test_registration_id_column_is_protected_once(self):
        spreadsheet = MagicMock()
        spreadsheet.fetch_sheet_metadata.return_value = {"sheets": []}
        worksheet = MagicMock(id=42, spreadsheet=spreadsheet)
        header = ["Order", "Registration ID"]

        ensure_registration_id_protected(
            worksheet,
            header,
            editor_email="service@example.com",
        )

        worksheet.add_protected_range.assert_called_once_with(
            "B:B",
            editor_users_emails=["service@example.com"],
            description="Innovate to Grow application-managed Registration ID",
            warning_only=False,
            requesting_user_can_edit=True,
        )

    def test_matching_registration_id_protection_is_reused(self):
        spreadsheet = MagicMock()
        spreadsheet.fetch_sheet_metadata.return_value = {
            "sheets": [
                {
                    "properties": {"sheetId": 42},
                    "protectedRanges": [
                        {
                            "description": "Innovate to Grow application-managed Registration ID",
                            "range": {
                                "startColumnIndex": 1,
                                "endColumnIndex": 2,
                            },
                        }
                    ],
                }
            ]
        }
        worksheet = MagicMock(id=42, spreadsheet=spreadsheet)

        ensure_registration_id_protected(
            worksheet,
            ["Order", "Registration ID"],
            editor_email="service@example.com",
        )

        worksheet.add_protected_range.assert_not_called()
