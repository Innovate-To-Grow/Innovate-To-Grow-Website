from datetime import timedelta
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.authn.models import ContactEmail
from apps.cms.admin.news.feed_source import NewsFeedSourceAdmin
from apps.cms.admin.news.sync_log import NewsSyncLogAdmin
from apps.cms.models import NewsArticle, NewsFeedSource, NewsSyncLog
from apps.event.tests.helpers import make_admin, make_superuser

Member = get_user_model()


class NewsArticleAdminTest(TestCase):
    def setUp(self):
        self.admin = Member.objects.create_superuser(
            password="testpass123",
            first_name="News",
            last_name="Admin",
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

    def test_changelist_accessible(self):
        resp = self.client.get(reverse("admin:cms_newsfeedsource_changelist"))
        self.assertEqual(resp.status_code, 200)

    @patch("apps.cms.admin.news.feed_source.sync_news")
    def test_sync_all_feeds(self, mock_sync):
        mock_sync.return_value = {"created": 5, "updated": 2, "errors": []}
        resp = self.client.get(reverse("admin:cms_newsfeedsource_sync_all_feeds"))
        self.assertEqual(resp.status_code, 302)
        mock_sync.assert_called_once_with(feed_url=self.source.feed_url, source_key="ucmerced")

    @patch("apps.cms.admin.news.feed_source.sync_news")
    def test_sync_all_feeds_with_errors(self, mock_sync):
        mock_sync.return_value = {"created": 0, "updated": 0, "errors": ["bad item"]}
        resp = self.client.get(reverse("admin:cms_newsfeedsource_sync_all_feeds"))
        self.assertEqual(resp.status_code, 302)

    @patch("apps.cms.admin.news.feed_source.sync_news")
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

    @patch("apps.cms.admin.news.feed_source.sync_news")
    def test_sync_creates_log(self, mock_sync):
        mock_sync.return_value = {"created": 2, "updated": 1, "errors": []}
        self.client.get(reverse("admin:cms_newsfeedsource_sync_all_feeds"))
        self.assertEqual(NewsSyncLog.objects.count(), 1)
        log = NewsSyncLog.objects.first()
        self.assertEqual(log.feed_source, self.source)
        self.assertEqual(log.articles_created, 2)
        self.assertEqual(log.articles_updated, 1)
        self.assertFalse(log.has_errors)

    @patch("apps.cms.admin.news.feed_source.sync_news")
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

    def test_sync_this_feed_inactive_source_warns(self):
        self.source.is_active = False
        self.source.save()
        resp = self.client.get(reverse("admin:cms_newsfeedsource_sync_this_feed", args=[self.source.pk]))
        self.assertEqual(resp.status_code, 302)
        # No sync log is created for an inactive feed.
        self.assertEqual(NewsSyncLog.objects.count(), 0)

    @patch("apps.cms.admin.news.feed_source.sync_news")
    def test_sync_this_feed_with_errors_warns(self, mock_sync):
        mock_sync.return_value = {"created": 0, "updated": 0, "errors": ["broken"]}
        resp = self.client.get(reverse("admin:cms_newsfeedsource_sync_this_feed", args=[self.source.pk]))
        self.assertEqual(resp.status_code, 302)
        log = NewsSyncLog.objects.get()
        self.assertTrue(log.has_errors)
        self.assertIn("broken", log.errors_text)


class NewsFeedSourceAdminDisplayTests(TestCase):
    def setUp(self):
        self.admin = NewsFeedSourceAdmin(NewsFeedSource, AdminSite())

    def test_status_badge_active(self):
        source = NewsFeedSource(name="A", source_key="a", feed_url="https://x/feed", is_active=True)
        self.assertEqual(self.admin.status_badge(source), ("Active", "success"))

    def test_status_badge_inactive(self):
        source = NewsFeedSource(name="B", source_key="b", feed_url="https://x/feed", is_active=False)
        self.assertEqual(self.admin.status_badge(source), ("Inactive", "danger"))

    def test_sync_result_badge_never_synced(self):
        source = NewsFeedSource(name="C", source_key="c", feed_url="https://x/feed")
        self.assertEqual(self.admin.sync_result_badge(source), ("Never synced", "info"))

    def test_sync_result_badge_errors(self):
        source = NewsFeedSource(
            name="D",
            source_key="d",
            feed_url="https://x/feed",
            last_synced_at=timezone.now(),
            last_sync_errors="something failed",
        )
        self.assertEqual(self.admin.sync_result_badge(source), ("Errors", "warning"))

    def test_sync_result_badge_success(self):
        source = NewsFeedSource(
            name="E",
            source_key="e",
            feed_url="https://x/feed",
            last_synced_at=timezone.now(),
            last_sync_errors="",
        )
        self.assertEqual(self.admin.sync_result_badge(source), ("Success", "success"))

    def test_time_since_sync_never(self):
        source = NewsFeedSource(name="F", source_key="f", feed_url="https://x/feed")
        self.assertEqual(self.admin.time_since_sync(source), "-")

    def test_time_since_sync_with_timestamp(self):
        source = NewsFeedSource(
            name="G",
            source_key="g",
            feed_url="https://x/feed",
            last_synced_at=timezone.now() - timedelta(hours=2),
        )
        result = self.admin.time_since_sync(source)
        self.assertTrue(result.endswith("ago"))
        self.assertIn("hour", result)


class NewsSyncLogAdminDisplayTests(TestCase):
    def setUp(self):
        self.admin = NewsSyncLogAdmin(NewsSyncLog, AdminSite())
        self.source = NewsFeedSource.objects.create(name="Log Source", source_key="logsrc", feed_url="https://x/feed")

    def test_has_errors_display_true(self):
        log = NewsSyncLog.objects.create(feed_source=self.source, started_at=timezone.now(), errors_text="boom")
        self.assertTrue(self.admin.has_errors_display(log))

    def test_has_errors_display_false(self):
        log = NewsSyncLog.objects.create(feed_source=self.source, started_at=timezone.now(), errors_text="")
        self.assertFalse(self.admin.has_errors_display(log))


class NewsSyncLogAdminDeletePermissionTests(TestCase):
    """The read-only sync-log admin re-enables delete only for cms-app members."""

    def setUp(self):
        self.admin = NewsSyncLogAdmin(NewsSyncLog, AdminSite())
        self.factory = RequestFactory()

    def _request(self, user):
        request = self.factory.get("/admin/cms/newssynclog/")
        request.user = user
        return request

    def test_delete_allowed_for_cms_staff(self):
        user = make_admin(apps=["cms"], email="cms-log@example.com")
        self.assertTrue(self.admin.has_delete_permission(self._request(user)))

    def test_delete_denied_for_other_app_staff(self):
        user = make_admin(apps=["event"], email="event-log@example.com")
        self.assertFalse(self.admin.has_delete_permission(self._request(user)))

    def test_delete_allowed_for_superuser(self):
        user = make_superuser(email="master-log@example.com")
        self.assertTrue(self.admin.has_delete_permission(self._request(user)))


class NewsSyncLogAdminTest(TestCase):
    def setUp(self):
        self.admin = Member.objects.create_superuser(
            password="testpass123",
            first_name="Log",
            last_name="Admin",
        )
        ContactEmail.objects.get_or_create(
            member=self.admin, email_address="admin@test.com", defaults={"email_type": "primary", "verified": True}
        )
        self.client.login(username="admin@test.com", password="testpass123")

    def test_changelist_accessible(self):
        resp = self.client.get(reverse("admin:cms_newssynclog_changelist"))
        self.assertEqual(resp.status_code, 200)
