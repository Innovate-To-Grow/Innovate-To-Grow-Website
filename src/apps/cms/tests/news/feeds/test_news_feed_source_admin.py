from datetime import timedelta
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.messages import get_messages
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.authn.models import ContactEmail
from apps.cms.admin.news.feed_source import NewsFeedSourceAdmin
from apps.cms.models import NewsArticle, NewsFeedSource, NewsSyncLog
from apps.cms.tests.news.site.test_admin import Member


class _NewsFeedSourceAdminCase(TestCase):
    def setUp(self):
        self.admin = Member.objects.create_superuser(
            password="testpass123",
            first_name="Feed",
            last_name="Admin",
        )
        ContactEmail.objects.get_or_create(
            member=self.admin, email_address="admin@test.com", defaults={"email_type": "primary", "verified": True}
        )
        self.client.login(username="admin@test.com", password="testpass123")
        self.source = NewsFeedSource.objects.create(
            name="UC Merced",
            feed_url="https://news.ucmerced.edu/taxonomy/term/221/all/feed",
            source_key="ucmerced",
            is_active=True,
        )


class NewsFeedSourceAdminTest(_NewsFeedSourceAdminCase):
    def test_changelist_accessible(self):
        resp = self.client.get(reverse("admin:cms_newsfeedsource_changelist"))
        self.assertEqual(resp.status_code, 200)

    def test_changelist_shows_last_sync_error_detail(self):
        self.source.last_sync_errors = "Error: HTTP Error 403: Forbidden (Akamai reference 1.abc)"
        self.source.save(update_fields=["last_sync_errors"])

        response = self.client.get(reverse("admin:cms_newsfeedsource_changelist"))

        self.assertContains(response, "HTTP Error 403: Forbidden (Akamai reference 1.abc)")

    def test_source_key_is_immutable_after_source_creation(self):
        model_admin = NewsFeedSourceAdmin(NewsFeedSource, AdminSite())
        request = RequestFactory().get("/")

        self.assertNotIn("source_key", model_admin.get_readonly_fields(request, obj=None))
        self.assertIn("source_key", model_admin.get_readonly_fields(request, obj=self.source))

    @patch("apps.cms.services.news.orchestrator.sync_news")
    def test_sync_all_feeds(self, mock_sync):
        mock_sync.return_value = {"created": 5, "updated": 2, "errors": []}
        resp = self.client.get(reverse("admin:cms_newsfeedsource_sync_all_feeds"))
        self.assertEqual(resp.status_code, 302)
        mock_sync.assert_called_once_with(feed_url=self.source.feed_url, source_key="ucmerced")

    @patch("apps.cms.services.news.orchestrator.sync_news")
    def test_sync_all_feeds_with_errors(self, mock_sync):
        mock_sync.return_value = {"created": 0, "updated": 0, "errors": ["bad item"]}
        response = self.client.get(reverse("admin:cms_newsfeedsource_sync_all_feeds"))

        self.assertEqual(response.status_code, 302)
        stored_messages = list(get_messages(response.wsgi_request))
        self.assertEqual(stored_messages[0].level_tag, "error")
        self.assertIn("Details: Error: UC Merced: bad item", str(stored_messages[0]))

    @patch("apps.cms.services.news.orchestrator.sync_news")
    def test_sync_this_feed(self, mock_sync):
        mock_sync.return_value = {"created": 3, "updated": 1, "errors": []}
        resp = self.client.get(reverse("admin:cms_newsfeedsource_sync_this_feed", args=[self.source.pk]))
        self.assertEqual(resp.status_code, 302)
        mock_sync.assert_called_once_with(feed_url=self.source.feed_url, source_key="ucmerced")

    def test_sync_all_feeds_no_active(self):
        self.source.is_active = False
        self.source.save()
        resp = self.client.get(reverse("admin:cms_newsfeedsource_sync_all_feeds"))
        self.assertEqual(resp.status_code, 302)

    @patch("apps.cms.services.news.orchestrator.sync_news")
    def test_sync_creates_log(self, mock_sync):
        mock_sync.return_value = {"created": 2, "updated": 1, "errors": []}
        self.client.get(reverse("admin:cms_newsfeedsource_sync_all_feeds"))
        self.assertEqual(NewsSyncLog.objects.count(), 1)
        log = NewsSyncLog.objects.first()
        self.assertEqual(log.feed_source, self.source)
        self.assertEqual(log.articles_created, 2)
        self.assertEqual(log.articles_updated, 1)
        self.assertFalse(log.has_errors)
        self.source.refresh_from_db()
        self.assertLessEqual(log.started_at, self.source.last_synced_at)

    @patch("apps.cms.services.news.orchestrator.sync_news")
    def test_sync_creates_log_with_errors(self, mock_sync):
        mock_sync.return_value = {"created": 0, "updated": 0, "errors": ["fail1", "fail2"]}
        self.client.get(reverse("admin:cms_newsfeedsource_sync_all_feeds"))
        log = NewsSyncLog.objects.first()
        self.assertTrue(log.has_errors)
        self.assertIn("fail1", log.errors_text)
        self.source.refresh_from_db()
        self.assertIsNone(self.source.last_synced_at)

    @patch("apps.cms.services.news.orchestrator.sync_news")
    def test_failed_sync_preserves_last_success_time(self, mock_sync):
        previous_success = timezone.now() - timedelta(days=1)
        self.source.last_synced_at = previous_success
        self.source.save(update_fields=["last_synced_at"])
        mock_sync.return_value = {"created": 0, "updated": 0, "errors": ["feed unavailable"]}

        self.client.get(reverse("admin:cms_newsfeedsource_sync_this_feed", args=[self.source.pk]))

        self.source.refresh_from_db()
        self.assertEqual(self.source.last_synced_at, previous_success)
        self.assertEqual(self.source.last_sync_errors, "Error: feed unavailable")
        self.assertEqual(NewsSyncLog.objects.count(), 1)

    @patch("apps.cms.services.news.orchestrator.sync_news")
    def test_fatal_error_with_warning_prefix_is_still_persisted_as_error(self, mock_sync):
        mock_sync.return_value = {
            "created": 0,
            "updated": 0,
            "errors": ["Warning: misleading upstream text"],
            "warnings": [],
        }

        self.client.get(reverse("admin:cms_newsfeedsource_sync_this_feed", args=[self.source.pk]))

        self.source.refresh_from_db()
        log = NewsSyncLog.objects.get()
        self.assertEqual(self.source.last_sync_errors, "Error: Warning: misleading upstream text")
        self.assertTrue(log.has_errors)

    def test_article_count_display(self):
        NewsArticle.objects.create(
            source_guid="g1",
            title="Test",
            source_url="https://example.com/1",
            published_at="2025-01-01T00:00:00Z",
            source="ucmerced",
        )
        resp = self.client.get(reverse("admin:cms_newsfeedsource_changelist"))
        self.assertContains(resp, ">1</a>")

    def test_sync_this_feed_inactive_source_warns(self):
        self.source.is_active = False
        self.source.save()
        resp = self.client.get(reverse("admin:cms_newsfeedsource_sync_this_feed", args=[self.source.pk]))
        self.assertEqual(resp.status_code, 302)
        # No sync log is created for an inactive feed.
        self.assertEqual(NewsSyncLog.objects.count(), 0)

    @patch("apps.cms.services.news.orchestrator.sync_news")
    def test_sync_this_feed_with_errors_shows_error_details(self, mock_sync):
        mock_sync.return_value = {"created": 0, "updated": 0, "errors": ["broken"]}
        response = self.client.get(reverse("admin:cms_newsfeedsource_sync_this_feed", args=[self.source.pk]))

        self.assertEqual(response.status_code, 302)
        stored_messages = list(get_messages(response.wsgi_request))
        self.assertEqual(stored_messages[0].level_tag, "error")
        self.assertIn("Details: Error: UC Merced: broken", str(stored_messages[0]))
        log = NewsSyncLog.objects.get()
        self.assertTrue(log.has_errors)
        self.assertIn("broken", log.errors_text)
