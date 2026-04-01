from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from authn.models import ContactEmail
from cms.models import NewsArticle, NewsFeedSource, NewsSyncLog

Member = get_user_model()


class NewsArticleAdminTest(TestCase):
    def setUp(self):
        self.admin = Member.objects.create_superuser(
            password="testpass123",
        )
        ContactEmail.objects.get_or_create(
            member=self.admin, email_address="admin@test.com", defaults={"email_type": "primary", "verified": True}
        )
        self.client.login(username="admin@test.com", password="testpass123")

    def test_changelist_accessible(self):
        resp = self.client.get(reverse("admin:cms_newsarticle_changelist"))
        self.assertEqual(resp.status_code, 200)


class NewsFeedSourceAdminTest(TestCase):
    def setUp(self):
        self.admin = Member.objects.create_superuser(
            password="testpass123",
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

    def test_changelist_accessible(self):
        resp = self.client.get(reverse("admin:cms_newsfeedsource_changelist"))
        self.assertEqual(resp.status_code, 200)

    @patch("cms.admin.news.feed_source.sync_news")
    def test_sync_all_feeds(self, mock_sync):
        mock_sync.return_value = {"created": 5, "updated": 2, "errors": []}
        resp = self.client.get(reverse("admin:cms_newsfeedsource_sync_all_feeds"))
        self.assertEqual(resp.status_code, 302)
        mock_sync.assert_called_once_with(feed_url=self.source.feed_url, source_key="ucmerced")

    @patch("cms.admin.news.feed_source.sync_news")
    def test_sync_all_feeds_with_errors(self, mock_sync):
        mock_sync.return_value = {"created": 0, "updated": 0, "errors": ["bad item"]}
        resp = self.client.get(reverse("admin:cms_newsfeedsource_sync_all_feeds"))
        self.assertEqual(resp.status_code, 302)

    @patch("cms.admin.news.feed_source.sync_news")
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

    @patch("cms.admin.news.feed_source.sync_news")
    def test_sync_creates_log(self, mock_sync):
        mock_sync.return_value = {"created": 2, "updated": 1, "errors": []}
        self.client.get(reverse("admin:cms_newsfeedsource_sync_all_feeds"))
        self.assertEqual(NewsSyncLog.objects.count(), 1)
        log = NewsSyncLog.objects.first()
        self.assertEqual(log.feed_source, self.source)
        self.assertEqual(log.articles_created, 2)
        self.assertEqual(log.articles_updated, 1)
        self.assertFalse(log.has_errors)

    @patch("cms.admin.news.feed_source.sync_news")
    def test_sync_creates_log_with_errors(self, mock_sync):
        mock_sync.return_value = {"created": 0, "updated": 0, "errors": ["fail1", "fail2"]}
        self.client.get(reverse("admin:cms_newsfeedsource_sync_all_feeds"))
        log = NewsSyncLog.objects.first()
        self.assertTrue(log.has_errors)
        self.assertIn("fail1", log.errors_text)

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


class NewsSyncLogAdminTest(TestCase):
    def setUp(self):
        self.admin = Member.objects.create_superuser(
            password="testpass123",
        )
        ContactEmail.objects.get_or_create(
            member=self.admin, email_address="admin@test.com", defaults={"email_type": "primary", "verified": True}
        )
        self.client.login(username="admin@test.com", password="testpass123")

    def test_changelist_accessible(self):
        resp = self.client.get(reverse("admin:cms_newssynclog_changelist"))
        self.assertEqual(resp.status_code, 200)
