import json

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from sheets.models import GoogleSheetSource

Member = get_user_model()


class GoogleSheetSourceAdminImportExportTests(TestCase):
    def setUp(self):
        self.admin_user = Member.objects.create_superuser(
            username="sheetadmin",
            email="sheetadmin@example.com",
            password="testpass123",
        )
        self.client.login(username="sheetadmin", password="testpass123")

    def _make_bundle(self, sources):
        return json.dumps({"version": 1, "sources": sources}).encode("utf-8")

    def test_export_json_structure(self):
        source = GoogleSheetSource.objects.create(
            slug="current-event",
            title="Current Event",
            sheet_type="current-event",
            spreadsheet_id="spreadsheet-123",
            range_a1="Sheet1!A1:F20",
            tracks_spreadsheet_id="tracks-123",
            tracks_sheet_name="Tracks",
            semester_filter="2026 Spring",
            cache_ttl_seconds=600,
            is_active=True,
        )

        response = self.client.post(
            "/admin/sheets/googlesheetsource/",
            {"action": "export_sources", "_selected_action": [str(source.pk)]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")

        bundle = json.loads(response.content)
        self.assertEqual(bundle["version"], 1)
        self.assertEqual(len(bundle["sources"]), 1)
        exported = bundle["sources"][0]
        self.assertEqual(exported["slug"], "current-event")
        self.assertEqual(exported["title"], "Current Event")
        self.assertEqual(exported["sheet_type"], "current-event")
        self.assertEqual(exported["spreadsheet_id"], "spreadsheet-123")
        self.assertEqual(exported["range_a1"], "Sheet1!A1:F20")
        self.assertEqual(exported["tracks_spreadsheet_id"], "tracks-123")
        self.assertEqual(exported["tracks_sheet_name"], "Tracks")
        self.assertEqual(exported["semester_filter"], "2026 Spring")
        self.assertEqual(exported["cache_ttl_seconds"], 600)
        self.assertTrue(exported["is_active"])

    def test_import_creates_and_updates_sources(self):
        existing = GoogleSheetSource.objects.create(
            slug="past-projects",
            title="Past Projects",
            sheet_type="past-projects",
            spreadsheet_id="old-sheet",
            range_a1="Old!A1:C10",
            cache_ttl_seconds=300,
            is_active=True,
        )

        bundle = self._make_bundle(
            [
                {
                    "slug": "past-projects",
                    "title": "Past Projects Updated",
                    "sheet_type": "past-projects",
                    "spreadsheet_id": "new-sheet",
                    "range_a1": "Updated!A1:Z99",
                    "tracks_spreadsheet_id": "tracks-999",
                    "tracks_sheet_name": "Tracks 2026",
                    "semester_filter": "2026 Spring",
                    "cache_ttl_seconds": 900,
                    "is_active": False,
                },
                {
                    "slug": "archive-2026-spring",
                    "title": "Archive Spring 2026",
                    "sheet_type": "archive-event",
                    "spreadsheet_id": "archive-sheet",
                    "range_a1": "Archive!A1:Q50",
                    "tracks_spreadsheet_id": "",
                    "tracks_sheet_name": "",
                    "semester_filter": "",
                    "cache_ttl_seconds": 1200,
                    "is_active": True,
                },
            ]
        )
        upload = SimpleUploadedFile("sheet-sources.json", bundle, content_type="application/json")

        response = self.client.post(
            "/admin/sheets/googlesheetsource/import/",
            {"json_file": upload, "action": "execute"},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)

        existing.refresh_from_db()
        self.assertEqual(existing.title, "Past Projects Updated")
        self.assertEqual(existing.spreadsheet_id, "new-sheet")
        self.assertEqual(existing.range_a1, "Updated!A1:Z99")
        self.assertEqual(existing.tracks_spreadsheet_id, "tracks-999")
        self.assertEqual(existing.tracks_sheet_name, "Tracks 2026")
        self.assertEqual(existing.semester_filter, "2026 Spring")
        self.assertEqual(existing.cache_ttl_seconds, 900)
        self.assertFalse(existing.is_active)

        created = GoogleSheetSource.objects.filter(slug="archive-2026-spring").first()
        self.assertIsNotNone(created)
        self.assertEqual(created.title, "Archive Spring 2026")
        self.assertEqual(created.sheet_type, "archive-event")

    def test_import_dry_run_does_not_write_records(self):
        bundle = self._make_bundle(
            [
                {
                    "slug": "preview-only",
                    "title": "Preview Only",
                    "sheet_type": "current-event",
                    "spreadsheet_id": "preview-sheet",
                    "range_a1": "Preview!A1:B2",
                    "cache_ttl_seconds": 300,
                    "is_active": True,
                }
            ]
        )
        upload = SimpleUploadedFile("sheet-sources.json", bundle, content_type="application/json")

        response = self.client.post(
            "/admin/sheets/googlesheetsource/import/",
            {"json_file": upload, "action": "dry_run"},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(GoogleSheetSource.objects.filter(slug="preview-only").exists())
