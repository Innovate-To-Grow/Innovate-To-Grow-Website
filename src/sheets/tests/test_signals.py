"""Tests for sheets cache invalidation signal handlers."""

from django.core.cache import cache
from django.test import TestCase

from sheets.models import GoogleSheetSource


class SheetCacheInvalidationSignalTests(TestCase):
    """Verify that saving or deleting GoogleSheetSource clears the relevant cache keys."""

    def setUp(self):
        cache.clear()

    def test_sheet_source_save_clears_sheet_cache(self):
        with self.captureOnCommitCallbacks(execute=True):
            source = GoogleSheetSource.objects.create(
                slug="sig-sheet",
                title="Signal Sheet",
                sheet_type="current-event",
                spreadsheet_id="fake",
                range_a1="A1:Z1",
                is_active=True,
            )
        cache.set("sheets:sig-sheet:data", {"cached": True})
        cache.set("layout:data", {"cached": True})
        with self.captureOnCommitCallbacks(execute=True):
            source.title = "Updated"
            source.save()
        self.assertIsNone(cache.get("sheets:sig-sheet:data"))
        self.assertIsNone(cache.get("layout:data"))

    def test_sheet_source_delete_clears_sheet_cache(self):
        source = GoogleSheetSource.objects.create(
            slug="del-sheet",
            title="Delete Sheet",
            sheet_type="current-event",
            spreadsheet_id="fake",
            range_a1="A1:Z1",
            is_active=True,
        )
        cache.set("sheets:del-sheet:data", {"cached": True})
        cache.set("layout:data", {"cached": True})
        with self.captureOnCommitCallbacks(execute=True):
            source.delete()
        self.assertIsNone(cache.get("sheets:del-sheet:data"))
        self.assertIsNone(cache.get("layout:data"))
