import uuid
from unittest.mock import Mock, patch

from django.test import TestCase
from django.urls import reverse
from googleapiclient.errors import HttpError
from rest_framework import status
from rest_framework.test import APIClient

from ...models import GoogleSheet
from ...services import GoogleSheetsConfigError


class GoogleSheetDataViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.sheet = GoogleSheet.objects.create(
            name="Public Schedule",
            spreadsheet_id="spreadsheet-id",
            sheet_name="Sheet1",
            is_enabled=True,
        )
        self.url = reverse("pages:google-sheet-data", kwargs={"sheet_id": self.sheet.id})

    @patch("pages.views.google_sheets.fetch_sheet_values")
    def test_get_google_sheet_data_success(self, mocked_fetch_sheet_values):
        mocked_fetch_sheet_values.return_value = {
            "headers": ["Name", "Score"],
            "rows": [["Team A", "95"], ["Team B", "90"]],
        }

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["sheet_id"], str(self.sheet.id))
        self.assertEqual(response.data["sheet_name"], "Sheet1")
        self.assertEqual(response.data["headers"], ["Name", "Score"])
        self.assertEqual(response.data["rows"], [["Team A", "95"], ["Team B", "90"]])

    def test_disabled_google_sheet_returns_404(self):
        self.sheet.is_enabled = False
        self.sheet.save(update_fields=["is_enabled", "updated_at"])

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_missing_google_sheet_returns_404(self):
        url = reverse("pages:google-sheet-data", kwargs={"sheet_id": uuid.uuid4()})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch("pages.views.google_sheets.fetch_sheet_values")
    def test_google_api_error_returns_502(self, mocked_fetch_sheet_values):
        mocked_fetch_sheet_values.side_effect = HttpError(
            resp=Mock(status=503, reason="Bad Gateway"),
            content=b"upstream failure",
        )

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(response.data["detail"], "Failed to fetch Google Sheet data.")

    @patch("pages.views.google_sheets.fetch_sheet_values")
    def test_google_sheet_config_error_returns_500(self, mocked_fetch_sheet_values):
        mocked_fetch_sheet_values.side_effect = GoogleSheetsConfigError("Missing credentials")

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(response.data["detail"], "Google Sheets is not configured.")
