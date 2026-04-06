"""Tests for core admin mixins (timestamped, export)."""

import csv
import io
import json

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.utils import timezone

from cms.models import NewsArticle
from core.admin.mixins import (
    ExportMixin,
    ImportExportMixin,
    TimestampedAdminMixin,
)

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


class _TimestampAdmin(TimestampedAdminMixin, _MockSuperAdmin):
    pass


class _ImportExportAdmin(ImportExportMixin, _MockSuperAdmin):
    export_filename_prefix = "articles"


class _ExportCsvAdmin(ExportMixin, _MockSuperAdmin):
    pass


class TimestampedAdminMixinTest(TestCase):
    def setUp(self):
        self.admin = _TimestampAdmin()
        self.factory = RequestFactory()
        self.request = self.factory.get("/admin/")

    def test_readonly_includes_timestamp_fields(self):
        readonly = self.admin.get_readonly_fields(self.request)
        for field in ("created_at", "updated_at"):
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
