"""Tests for ProjectControlModel soft-delete and manager behaviour."""

from django.test import TestCase
from django.utils import timezone

from cms.models import NewsArticle


def _make_article(**kwargs):
    defaults = {
        "source": "test",
        "source_guid": f"guid-{timezone.now().timestamp()}",
        "title": "Test Article",
        "source_url": "https://example.com",
        "published_at": timezone.now(),
    }
    defaults.update(kwargs)
    return NewsArticle.objects.create(**defaults)


class SoftDeleteInstanceTest(TestCase):
    def test_delete_marks_as_deleted(self):
        article = _make_article()
        article.delete()
        article.refresh_from_db()

        self.assertTrue(article.is_deleted)
        self.assertIsNotNone(article.deleted_at)

    def test_deleted_record_excluded_from_default_manager(self):
        article = _make_article(source_guid="del-1")
        article.delete()

        self.assertFalse(NewsArticle.objects.filter(pk=article.pk).exists())

    def test_deleted_record_visible_via_all_objects(self):
        article = _make_article(source_guid="del-2")
        article.delete()

        self.assertTrue(NewsArticle.all_objects.filter(pk=article.pk).exists())

    def test_restore_clears_deleted_fields(self):
        article = _make_article(source_guid="del-3")
        article.delete()
        article.restore()
        article.refresh_from_db()

        self.assertFalse(article.is_deleted)
        self.assertIsNone(article.deleted_at)
        self.assertTrue(NewsArticle.objects.filter(pk=article.pk).exists())

    def test_hard_delete_removes_from_database(self):
        article = _make_article(source_guid="hard-1")
        pk = article.pk
        article.hard_delete()

        self.assertFalse(NewsArticle.all_objects.filter(pk=pk).exists())


class ManagerFilteringTest(TestCase):
    def setUp(self):
        self.active = _make_article(source_guid="active-1", title="Active")
        self.deleted = _make_article(source_guid="deleted-1", title="Deleted")
        self.deleted.delete()

    def test_objects_returns_only_active(self):
        qs = NewsArticle.objects.all()
        self.assertEqual(list(qs), [self.active])

    def test_all_objects_returns_everything(self):
        self.assertEqual(NewsArticle.all_objects.count(), 2)

    def test_deleted_manager_returns_only_deleted(self):
        qs = NewsArticle.objects.deleted()
        self.assertEqual(list(qs), [self.deleted])

    def test_with_deleted_returns_everything(self):
        self.assertEqual(NewsArticle.objects.with_deleted().count(), 2)


class QuerySetBulkOperationsTest(TestCase):
    def setUp(self):
        for i in range(3):
            _make_article(source_guid=f"bulk-{i}", title=f"Bulk {i}")

    def test_queryset_bulk_soft_delete(self):
        NewsArticle.objects.all().delete()

        self.assertEqual(NewsArticle.objects.count(), 0)
        self.assertEqual(NewsArticle.all_objects.count(), 3)

    def test_queryset_bulk_restore(self):
        NewsArticle.objects.all().delete()
        NewsArticle.all_objects.all().restore()

        self.assertEqual(NewsArticle.objects.count(), 3)

    def test_queryset_bulk_hard_delete(self):
        NewsArticle.objects.all().hard_delete()

        self.assertEqual(NewsArticle.all_objects.count(), 0)
