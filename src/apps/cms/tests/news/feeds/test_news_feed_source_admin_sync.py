from datetime import timedelta
from unittest.mock import patch

from django.contrib.messages import get_messages
from django.urls import reverse
from django.utils import timezone

from apps.cms.models import NewsSyncLog
from apps.cms.tests.news.feeds.test_news_feed_source_admin import _NewsFeedSourceAdminCase


class NewsFeedSourceAdminTest(_NewsFeedSourceAdminCase):
    @patch("apps.cms.services.news.orchestrator.sync_news")
    def test_sync_this_feed_with_warnings_uses_warning_message(self, mock_sync):
        mock_sync.return_value = {
            "created": 1,
            "updated": 0,
            "errors": [],
            "warnings": ["Article body used the RSS fallback"],
        }

        response = self.client.get(reverse("admin:cms_newsfeedsource_sync_this_feed", args=[self.source.pk]))

        stored_messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(stored_messages), 1)
        self.assertEqual(stored_messages[0].level_tag, "warning")
        self.assertIn("1 warning(s)", str(stored_messages[0]))
        self.assertIn("Details: Warning: UC Merced: Article body used the RSS fallback", str(stored_messages[0]))
        self.source.refresh_from_db()
        log = NewsSyncLog.objects.get()
        self.assertEqual(self.source.last_sync_errors, "Warning: Article body used the RSS fallback")
        self.assertEqual(log.errors_text, "Warning: Article body used the RSS fallback")
        self.assertFalse(log.has_errors)
        self.assertIsNotNone(self.source.last_synced_at)

    @patch("apps.cms.services.news.orchestrator.sync_news")
    def test_sync_this_feed_separates_error_and_warning_details(self, mock_sync):
        mock_sync.return_value = {
            "created": 0,
            "updated": 0,
            "errors": ["HTTP Error 403: Forbidden"],
            "warnings": ["Article body used the RSS fallback"],
        }

        response = self.client.get(reverse("admin:cms_newsfeedsource_sync_this_feed", args=[self.source.pk]))

        stored_messages = list(get_messages(response.wsgi_request))
        self.assertEqual([message.level_tag for message in stored_messages], ["error", "warning"])
        self.assertIn("Details: Error: UC Merced: HTTP Error 403: Forbidden", str(stored_messages[0]))
        self.assertNotIn("RSS fallback", str(stored_messages[0]))
        self.assertIn(
            "Details: Warning: UC Merced: Article body used the RSS fallback",
            str(stored_messages[1]),
        )

    @patch("apps.cms.services.news.orchestrator.sync_news")
    def test_sync_error_message_limits_items(self, mock_sync):
        mock_sync.return_value = {
            "created": 0,
            "updated": 0,
            "errors": [f"failure {index}" for index in range(5)],
            "warnings": [],
        }

        response = self.client.get(reverse("admin:cms_newsfeedsource_sync_this_feed", args=[self.source.pk]))

        message = str(list(get_messages(response.wsgi_request))[0])
        self.assertIn("failure 0", message)
        self.assertIn("failure 2", message)
        self.assertNotIn("failure 3", message)
        self.assertIn("+2 more; see Last Sync Status or sync log for full details", message)

    @patch("apps.cms.services.news.orchestrator.sync_news")
    def test_sync_error_message_truncates_long_detail(self, mock_sync):
        mock_sync.return_value = {
            "created": 0,
            "updated": 0,
            "errors": ["x" * 3000],
            "warnings": [],
        }

        response = self.client.get(reverse("admin:cms_newsfeedsource_sync_this_feed", args=[self.source.pk]))

        message = str(list(get_messages(response.wsgi_request))[0])
        self.assertLess(len(message), 1350)
        self.assertIn("truncated; see Last Sync Status or sync log for full details", message)

    @patch("apps.cms.services.news.orchestrator.sync_news")
    def test_sync_error_detail_is_html_escaped(self, mock_sync):
        mock_sync.return_value = {
            "created": 0,
            "updated": 0,
            "errors": ["<script>alert(1)</script>"],
            "warnings": [],
        }

        response = self.client.get(
            reverse("admin:cms_newsfeedsource_sync_this_feed", args=[self.source.pk]),
            follow=True,
        )

        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")

    @patch("apps.cms.services.news.orchestrator.sync_news")
    def test_sync_diagnostics_are_single_line_and_warning_stays_nonfatal(self, mock_sync):
        mock_sync.return_value = {
            "created": 0,
            "updated": 0,
            "errors": [],
            "warnings": ["article fallback\nupstream detail"],
        }

        self.client.get(reverse("admin:cms_newsfeedsource_sync_this_feed", args=[self.source.pk]))

        self.source.refresh_from_db()
        log = NewsSyncLog.objects.get()
        self.assertEqual(self.source.last_sync_errors, "Warning: article fallback upstream detail")
        self.assertFalse(log.has_errors)

    @patch("apps.cms.services.news.orchestrator.sync_news")
    def test_sync_log_uses_attempt_start_time(self, mock_sync):
        mock_sync.return_value = {"created": 1, "updated": 0, "errors": [], "warnings": []}
        started_at = timezone.now() - timedelta(seconds=5)
        completed_at = timezone.now()

        with (
            patch("apps.cms.services.news.orchestrator.timezone") as mock_timezone,
            patch("apps.cms.services.news.orchestrator.time.monotonic", side_effect=[10.0, 12.345]),
        ):
            mock_timezone.now.side_effect = [started_at, completed_at]
            self.client.get(reverse("admin:cms_newsfeedsource_sync_this_feed", args=[self.source.pk]))

        log = NewsSyncLog.objects.get()
        self.source.refresh_from_db()
        self.assertEqual(log.started_at, started_at)
        self.assertEqual(log.duration_seconds, 2.35)
        self.assertEqual(self.source.last_synced_at, completed_at)
