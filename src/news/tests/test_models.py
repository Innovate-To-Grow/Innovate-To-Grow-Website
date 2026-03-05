from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from news.models import NewsArticle


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
