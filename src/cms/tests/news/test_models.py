from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from cms.models import NewsArticle, NewsFeedSource, NewsSyncLog


class NewsArticleModelTest(TestCase):
    def test_create_article(self):
        article = NewsArticle.objects.create(
            source_guid="test-guid-123",
            title="Test Article",
            source_url="https://example.com/article",
            summary="A test summary.",
            published_at=timezone.now(),
        )
        self.assertEqual(str(article), "Test Article")
        self.assertEqual(article.source, "ucmerced")

    def test_ordering(self):
        now = timezone.now()
        older = NewsArticle.objects.create(
            source_guid="old",
            title="Older",
            source_url="https://example.com/old",
            published_at=now - timezone.timedelta(days=1),
        )
        newer = NewsArticle.objects.create(
            source_guid="new",
            title="Newer",
            source_url="https://example.com/new",
            published_at=now,
        )
        articles = list(NewsArticle.objects.all())
        self.assertEqual(articles[0], newer)
        self.assertEqual(articles[1], older)

    def test_unique_source_guid(self):
        NewsArticle.objects.create(
            source_guid="unique-guid",
            title="First",
            source_url="https://example.com/1",
            published_at=timezone.now(),
        )
        with self.assertRaises(IntegrityError):
            NewsArticle.objects.create(
                source_guid="unique-guid",
                title="Duplicate",
                source_url="https://example.com/2",
                published_at=timezone.now(),
            )

    def test_soft_delete(self):
        article = NewsArticle.objects.create(
            source_guid="soft-del",
            title="Soft Delete",
            source_url="https://example.com/soft",
            published_at=timezone.now(),
        )
        article.delete()
        self.assertEqual(NewsArticle.objects.count(), 0)
        self.assertEqual(NewsArticle.all_objects.count(), 1)


class NewsFeedSourceModelTest(TestCase):
    def test_source_key_unique(self):
        NewsFeedSource.objects.create(
            name="Source A",
            feed_url="https://example.com/feed-a",
            source_key="source-a",
        )
        with self.assertRaises(IntegrityError):
            NewsFeedSource.objects.create(
                name="Source B",
                feed_url="https://example.com/feed-b",
                source_key="source-a",
            )

    def test_source_key_default(self):
        source = NewsFeedSource.objects.create(
            name="Default",
            feed_url="https://example.com/feed",
        )
        self.assertEqual(source.source_key, "ucmerced")


class NewsSyncLogModelTest(TestCase):
    def setUp(self):
        self.source = NewsFeedSource.objects.create(
            name="Test Source",
            feed_url="https://example.com/feed",
            source_key="test-source",
        )

    def test_create_sync_log(self):
        log = NewsSyncLog.objects.create(
            feed_source=self.source,
            started_at=timezone.now(),
            duration_seconds=1.5,
            articles_created=5,
            articles_updated=3,
        )
        self.assertEqual(log.articles_created, 5)
        self.assertEqual(log.articles_updated, 3)

    def test_has_errors_true(self):
        log = NewsSyncLog.objects.create(
            feed_source=self.source,
            started_at=timezone.now(),
            errors_text="Something went wrong",
        )
        self.assertTrue(log.has_errors)

    def test_has_errors_false(self):
        log = NewsSyncLog.objects.create(
            feed_source=self.source,
            started_at=timezone.now(),
            errors_text="",
        )
        self.assertFalse(log.has_errors)

    def test_str(self):
        now = timezone.now()
        log = NewsSyncLog.objects.create(
            feed_source=self.source,
            started_at=now,
        )
        self.assertIn("Test Source", str(log))

    def test_ordering(self):
        now = timezone.now()
        older = NewsSyncLog.objects.create(
            feed_source=self.source,
            started_at=now - timezone.timedelta(hours=1),
        )
        newer = NewsSyncLog.objects.create(
            feed_source=self.source,
            started_at=now,
        )
        logs = list(NewsSyncLog.objects.all())
        self.assertEqual(logs[0], newer)
        self.assertEqual(logs[1], older)
