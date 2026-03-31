"""Tests for core admin mixins (soft-delete, versioning, timestamped, export)."""

import csv
import io
import json

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase
from django.utils import timezone

from cms.models import NewsArticle
from core.admin.mixins import ExportMixin, ImportExportMixin, SoftDeleteAdminMixin, TimestampedAdminMixin, VersionControlAdminMixin

User = get_user_model()


def _make_article(**kwargs):
    defaults = {
        "source": "test",
        "source_guid": f"guid-{timezone.now().timestamp()}",
        "title": "Test",
        "source_url": "https://example.com",
        "published_at": timezone.now(),
    }
    defaults.update(kwargs)
    return NewsArticle.objects.create(**defaults)


class _MockSuperAdmin:
    """Minimal stand-in for ModelAdmin methods that mixins call via super()."""

    model = NewsArticle

    def get_queryset(self, request):
        return NewsArticle.objects.all()

    def get_list_display(self, request):
        return ["__str__"]

    def get_list_filter(self, request):
        return []

    def get_readonly_fields(self, request, obj=None):
        return []

    def get_actions(self, request):
        return {}

    def save_model(self, request, obj, form, change):
        obj.save()


class _SoftDeleteAdmin(SoftDeleteAdminMixin, _MockSuperAdmin):
    pass


class _VersionAdmin(VersionControlAdminMixin, _MockSuperAdmin):
    pass


class _TimestampAdmin(TimestampedAdminMixin, _MockSuperAdmin):
    pass


class _ImportExportAdmin(ImportExportMixin, _MockSuperAdmin):
    export_filename_prefix = "articles"


class _ExportCsvAdmin(ExportMixin, _MockSuperAdmin):
    pass


class SoftDeleteAdminMixinTest(TestCase):
    def setUp(self):
        self.admin = _SoftDeleteAdmin()
        self.factory = RequestFactory()
        self.request = self.factory.get("/admin/")

    def test_queryset_includes_deleted(self):
        active = _make_article(source_guid="sd-active")
        deleted = _make_article(source_guid="sd-deleted")
        deleted.delete()

        qs = self.admin.get_queryset(self.request)
        self.assertIn(active, qs)
        self.assertIn(deleted, qs)

    def test_list_display_adds_deletion_status(self):
        display = self.admin.get_list_display(self.request)
        self.assertIn("deletion_status", display)

    def test_list_filter_adds_is_deleted(self):
        filters = self.admin.get_list_filter(self.request)
        self.assertIn("is_deleted", filters)

    def test_deletion_status_active(self):
        article = _make_article()
        result = self.admin.deletion_status(article)
        self.assertIn("Active", result)

    def test_deletion_status_deleted(self):
        article = _make_article()
        article.is_deleted = True
        result = self.admin.deletion_status(article)
        self.assertIn("Deleted", result)

    def _request_with_messages(self):
        request = self.factory.post("/admin/")
        request.session = "session"
        request._messages = FallbackStorage(request)
        return request

    def test_restore_selected_action(self):
        article = _make_article()
        article.delete()
        qs = NewsArticle.all_objects.filter(pk=article.pk)

        self.admin.restore_selected(self._request_with_messages(), qs)
        article.refresh_from_db()
        self.assertFalse(article.is_deleted)

    def test_soft_delete_selected_action(self):
        article = _make_article()
        qs = NewsArticle.objects.filter(pk=article.pk)

        self.admin.soft_delete_selected(self._request_with_messages(), qs)
        article.refresh_from_db()
        self.assertTrue(article.is_deleted)


class VersionControlAdminMixinTest(TestCase):
    def setUp(self):
        self.admin = _VersionAdmin()
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username="admin", password="pass")

    def test_save_model_creates_version_on_change(self):
        article = _make_article()
        request = self.factory.post("/admin/")
        request.user = self.user

        self.admin.save_model(request, article, form=None, change=True)

        self.assertEqual(article.version, 1)
        self.assertEqual(article.get_versions().count(), 1)

    def test_save_model_skips_version_on_create(self):
        article = _make_article()
        request = self.factory.post("/admin/")
        request.user = self.user

        self.admin.save_model(request, article, form=None, change=False)

        self.assertEqual(article.version, 0)

    def test_version_count_display(self):
        article = _make_article()
        result = self.admin.version_count(article)
        self.assertIn("0 versions", result)


class TimestampedAdminMixinTest(TestCase):
    def setUp(self):
        self.admin = _TimestampAdmin()
        self.factory = RequestFactory()
        self.request = self.factory.get("/admin/")

    def test_readonly_includes_timestamp_fields(self):
        readonly = self.admin.get_readonly_fields(self.request)
        for field in ("created_at", "updated_at", "deleted_at"):
            self.assertIn(field, readonly)

    def test_list_display_includes_created_at(self):
        display = self.admin.get_list_display(self.request)
        self.assertIn("created_at", display)


class ImportExportMixinTest(TestCase):
    def setUp(self):
        self.admin = _ImportExportAdmin()
        self.factory = RequestFactory()
        self.request = self.factory.get("/admin/")

    def test_export_as_json(self):
        a1 = _make_article(source_guid="ie-1", title="First")
        a2 = _make_article(source_guid="ie-2", title="Second")
        qs = NewsArticle.objects.filter(pk__in=[a1.pk, a2.pk])

        response = self.admin.export_as_json(self.request, qs)

        self.assertEqual(response["Content-Type"], "application/json")
        self.assertIn("attachment", response["Content-Disposition"])
        data = json.loads(response.content)
        self.assertEqual(len(data), 2)
        titles = {item["title"] for item in data}
        self.assertEqual(titles, {"First", "Second"})

    def test_actions_include_export_json(self):
        actions = self.admin.get_actions(self.request)
        self.assertIn("export_as_json", actions)


class ExportCsvMixinTest(TestCase):
    def setUp(self):
        self.admin = _ExportCsvAdmin()
        self.factory = RequestFactory()
        self.request = self.factory.get("/admin/")

    def test_export_to_csv(self):
        _make_article(source_guid="csv-1", title="CSV Test")
        qs = NewsArticle.objects.all()

        response = self.admin.export_to_csv(self.request, qs)

        self.assertEqual(response["Content-Type"], "text/csv")
        content = response.content.decode()
        reader = csv.reader(io.StringIO(content))
        rows = list(reader)
        self.assertGreaterEqual(len(rows), 2)  # header + data
        self.assertIn("title", rows[0])

    def test_actions_include_export_csv(self):
        actions = self.admin.get_actions(self.request)
        self.assertIn("export_to_csv", actions)
