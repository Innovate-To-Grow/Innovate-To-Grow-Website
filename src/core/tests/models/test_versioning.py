"""Tests for ProjectControlModel version control system."""

from django.test import TestCase
from django.utils import timezone

from cms.models import NewsArticle
from core.models.versioning import ModelVersion


def _make_article(**kwargs):
    defaults = {
        "source": "test",
        "source_guid": f"guid-{timezone.now().timestamp()}",
        "title": "Original Title",
        "source_url": "https://example.com",
        "published_at": timezone.now(),
    }
    defaults.update(kwargs)
    return NewsArticle.objects.create(**defaults)


class SaveVersionTest(TestCase):
    def test_save_version_increments_counter(self):
        article = _make_article()
        self.assertEqual(article.version, 0)

        article.save_version(comment="v1")
        self.assertEqual(article.version, 1)

        article.save_version(comment="v2")
        self.assertEqual(article.version, 2)

    def test_save_version_creates_model_version_record(self):
        article = _make_article()
        mv = article.save_version(comment="first save")

        self.assertIsInstance(mv, ModelVersion)
        self.assertEqual(mv.version_number, 1)
        self.assertEqual(mv.comment, "first save")
        self.assertIsNone(mv.created_by)

    def test_save_version_stores_field_data(self):
        article = _make_article(title="Snapshot Title", author="Alice")
        mv = article.save_version()

        self.assertEqual(mv.data["title"], "Snapshot Title")
        self.assertEqual(mv.data["author"], "Alice")

    def test_save_version_excludes_control_fields(self):
        article = _make_article()
        mv = article.save_version()

        for excluded in ("id", "created_at", "updated_at", "is_deleted", "deleted_at", "version"):
            self.assertNotIn(excluded, mv.data, f"{excluded} should be excluded from version data")


class GetVersionsTest(TestCase):
    def test_get_versions_returns_newest_first(self):
        article = _make_article()
        article.save_version(comment="v1")
        article.title = "Changed"
        article.save()
        article.save_version(comment="v2")

        versions = article.get_versions()
        numbers = list(versions.values_list("version_number", flat=True))
        self.assertEqual(numbers, [2, 1])

    def test_get_version_by_number(self):
        article = _make_article(title="First")
        article.save_version(comment="v1")

        article.title = "Second"
        article.save()
        article.save_version(comment="v2")

        data = article.get_version(1)
        self.assertEqual(data["title"], "First")

        data = article.get_version(2)
        self.assertEqual(data["title"], "Second")

    def test_get_version_returns_none_for_missing(self):
        article = _make_article()
        self.assertIsNone(article.get_version(999))


class RollbackTest(TestCase):
    def test_rollback_restores_fields_on_instance(self):
        article = _make_article(title="Original", author="Alice")
        article.save_version(comment="v1")

        article.title = "Changed"
        article.author = "Bob"
        article.save()
        article.save_version(comment="v2")

        article.rollback(version_number=1)

        # Rollback applies deserialized fields to the in-memory instance.
        # Note: save_version only persists version/updated_at, so a full
        # save() is needed to persist the restored field values to the DB.
        self.assertEqual(article.title, "Original")
        self.assertEqual(article.author, "Alice")

    def test_rollback_saves_current_state_before_restoring(self):
        article = _make_article(title="Original")
        article.save_version(comment="v1")

        article.title = "Changed"
        article.save()

        article.rollback(version_number=1, save_current=True)

        # v1 = original, v2 = auto-save of "Changed", v3 = rollback to v1
        self.assertEqual(article.get_versions().count(), 3)

    def test_rollback_without_saving_current(self):
        article = _make_article(title="Original")
        article.save_version(comment="v1")

        article.title = "Changed"
        article.save()

        article.rollback(version_number=1, save_current=False)

        # v1 = original, v2 = rollback (no auto-save)
        self.assertEqual(article.get_versions().count(), 2)

    def test_rollback_raises_for_missing_version(self):
        article = _make_article()
        with self.assertRaises(ValueError):
            article.rollback(version_number=999)


class VersionDiffTest(TestCase):
    def test_diff_returns_changed_fields(self):
        article = _make_article(title="First", author="Alice")
        article.save_version()

        article.title = "Second"
        article.save()
        article.save_version()

        diff = article.get_version_diff(1, 2)
        self.assertIn("title", diff)
        self.assertEqual(diff["title"], ("First", "Second"))
        self.assertNotIn("author", diff)

    def test_diff_raises_for_missing_version(self):
        article = _make_article()
        article.save_version()

        with self.assertRaises(ValueError):
            article.get_version_diff(1, 999)
