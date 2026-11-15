"""Tests for the sync_news management command."""

from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.cms.models import NewsFeedSource, NewsSyncLog


class SyncNewsCommandTests(TestCase):
    def setUp(self):
        self.source = NewsFeedSource.objects.create(
            name="UC Merced",
            feed_url="https://news.ucmerced.edu/taxonomy/term/221/all/feed",
            source_key="ucmerced",
            is_active=True,
        )

    @patch("apps.cms.services.news.orchestrator.sync_news")
    def test_command_reports_created_and_updated(self, mock_sync):
        mock_sync.return_value = {"created": 4, "updated": 2, "errors": [], "warnings": []}
        out = StringIO()
        err = StringIO()

        call_command("sync_news", stdout=out, stderr=err)

        mock_sync.assert_called_once_with(feed_url=self.source.feed_url, source_key=self.source.source_key)
        output = out.getvalue()
        self.assertIn("Syncing 1 active news feed(s)...", output)
        self.assertIn("UC Merced: 4 created, 2 updated", output)
        self.assertIn("Sync complete: 4 created, 2 updated across 1 feed(s).", output)
        self.assertEqual(err.getvalue(), "")
        self.source.refresh_from_db()
        self.assertEqual(self.source.last_sync_created, 4)
        self.assertEqual(self.source.last_sync_updated, 2)
        self.assertEqual(NewsSyncLog.objects.count(), 1)

    @patch("apps.cms.services.news.orchestrator.sync_news")
    def test_command_writes_errors_and_exits_nonzero(self, mock_sync):
        mock_sync.return_value = {
            "created": 0,
            "updated": 0,
            "errors": ["item failed", "bad date"],
            "warnings": [],
        }
        out = StringIO()
        err = StringIO()

        with self.assertRaisesMessage(CommandError, "2 error(s)"):
            call_command("sync_news", stdout=out, stderr=err)

        error_output = err.getvalue()
        self.assertIn("item failed", error_output)
        self.assertIn("bad date", error_output)
        self.source.refresh_from_db()
        self.assertIn("item failed", self.source.last_sync_errors)
        self.assertTrue(NewsSyncLog.objects.get().has_errors)

    @patch("apps.cms.services.news.orchestrator.sync_news")
    def test_command_warnings_do_not_fail(self, mock_sync):
        mock_sync.return_value = {
            "created": 1,
            "updated": 0,
            "errors": [],
            "warnings": ["Article body used the RSS fallback"],
        }
        out = StringIO()
        err = StringIO()

        call_command("sync_news", stdout=out, stderr=err)

        self.assertIn("Article body used the RSS fallback", err.getvalue())
        self.assertIn("1 warning(s)", err.getvalue())
        self.source.refresh_from_db()
        self.assertEqual(self.source.last_sync_errors, "Warning: Article body used the RSS fallback")
        self.assertEqual(NewsSyncLog.objects.get().errors_text, "Warning: Article body used the RSS fallback")

    @patch("apps.cms.services.news.orchestrator.sync_news")
    def test_command_syncs_each_active_source(self, mock_sync):
        second_source = NewsFeedSource.objects.create(
            name="Second Feed",
            feed_url="https://example.com/feed",
            source_key="second",
            is_active=True,
        )
        NewsFeedSource.objects.create(
            name="Inactive Feed",
            feed_url="https://example.com/inactive",
            source_key="inactive",
            is_active=False,
        )
        mock_sync.return_value = {"created": 0, "updated": 1, "errors": [], "warnings": []}

        call_command("sync_news", stdout=StringIO(), stderr=StringIO())

        self.assertEqual(mock_sync.call_count, 2)
        mock_sync.assert_any_call(feed_url=self.source.feed_url, source_key=self.source.source_key)
        mock_sync.assert_any_call(feed_url=second_source.feed_url, source_key=second_source.source_key)
        self.assertEqual(NewsSyncLog.objects.count(), 2)

    def test_command_fails_when_no_active_sources(self):
        self.source.is_active = False
        self.source.save(update_fields=["is_active"])
        out = StringIO()
        err = StringIO()

        with self.assertRaisesMessage(CommandError, "No active news feed sources found"):
            call_command("sync_news", stdout=out, stderr=err)

        self.assertEqual(NewsSyncLog.objects.count(), 0)
