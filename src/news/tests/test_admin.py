from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from news.models import NewsFeedSource

Member = get_user_model()


class NewsArticleAdminTest(TestCase):
    def setUp(self):
        self.admin = Member.objects.create_superuser(
            email="admin@test.com",
            username="admin",
            password="testpass123",
        )
        self.client.login(username="admin@test.com", password="testpass123")

    def test_changelist_accessible(self):
        resp = self.client.get(reverse("admin:news_newsarticle_changelist"))
        self.assertEqual(resp.status_code, 200)


class NewsFeedSourceAdminTest(TestCase):
    def setUp(self):
        self.admin = Member.objects.create_superuser(
            email="admin@test.com",
            username="admin",
            password="testpass123",
        )
        self.client.login(username="admin@test.com", password="testpass123")
        self.source = NewsFeedSource.objects.create(
            name="UC Merced",
            feed_url="https://news.ucmerced.edu/taxonomy/term/221/all/feed",
            is_active=True,
        )

    def test_changelist_accessible(self):
        resp = self.client.get(reverse("admin:news_newsfeedsource_changelist"))
        self.assertEqual(resp.status_code, 200)

    @patch("news.admin.feed_source.sync_news")
    def test_sync_all_feeds(self, mock_sync):
        mock_sync.return_value = {"created": 5, "updated": 2, "errors": []}
        resp = self.client.get(reverse("admin:news_newsfeedsource_sync_all_feeds"))
        self.assertEqual(resp.status_code, 302)
        mock_sync.assert_called_once_with(feed_url=self.source.feed_url)

    @patch("news.admin.feed_source.sync_news")
    def test_sync_all_feeds_with_errors(self, mock_sync):
        mock_sync.return_value = {"created": 0, "updated": 0, "errors": ["bad item"]}
        resp = self.client.get(reverse("admin:news_newsfeedsource_sync_all_feeds"))
        self.assertEqual(resp.status_code, 302)

    @patch("news.admin.feed_source.sync_news")
    def test_sync_this_feed(self, mock_sync):
        mock_sync.return_value = {"created": 3, "updated": 1, "errors": []}
        resp = self.client.get(reverse("admin:news_newsfeedsource_sync_this_feed", args=[self.source.pk]))
        self.assertEqual(resp.status_code, 302)
        mock_sync.assert_called_once_with(feed_url=self.source.feed_url)

    def test_sync_all_feeds_no_active(self):
        self.source.is_active = False
        self.source.save()
        resp = self.client.get(reverse("admin:news_newsfeedsource_sync_all_feeds"))
        self.assertEqual(resp.status_code, 302)
