"""Tests for the sync_news management command."""

from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase


class SyncNewsCommandTests(TestCase):
    @patch("apps.cms.management.commands.sync_news.sync_news")
    def test_command_reports_created_and_updated(self, mock_sync):
        mock_sync.return_value = {"created": 4, "updated": 2, "errors": []}
        out = StringIO()
        err = StringIO()

        call_command("sync_news", stdout=out, stderr=err)

        mock_sync.assert_called_once_with()
        output = out.getvalue()
        self.assertIn("Syncing news from RSS feed...", output)
        self.assertIn("Created: 4", output)
        self.assertIn("Updated: 2", output)
        self.assertIn("Sync complete.", output)
        self.assertEqual(err.getvalue(), "")

    @patch("apps.cms.management.commands.sync_news.sync_news")
    def test_command_writes_errors_to_stderr(self, mock_sync):
        mock_sync.return_value = {"created": 0, "updated": 0, "errors": ["item failed", "bad date"]}
        out = StringIO()
        err = StringIO()

        call_command("sync_news", stdout=out, stderr=err)

        error_output = err.getvalue()
        self.assertIn("item failed", error_output)
        self.assertIn("bad date", error_output)
        self.assertIn("Sync complete.", out.getvalue())
