"""Tests for core admin mixins (timestamped, data export)."""

import io

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.utils import timezone
from openpyxl import load_workbook

from apps.cms.models import NewsArticle
from apps.core.admin.mixins import (
    DataExportMixin,
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
    admin_site = AdminSite()

    @property
    def media(self):
        from django.forms import Media

        return Media()

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


class _DataExportAdmin(DataExportMixin, _MockSuperAdmin):
    pass


class _DataExportCustomAdmin(DataExportMixin, _MockSuperAdmin):
    export_fields = ["title", "source", "published_at"]
    export_filename = "custom_articles"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _load_xlsx(response_content):
    """Parse response bytes into an openpyxl Workbook."""
    return load_workbook(io.BytesIO(response_content))


def _make_post_request(factory, data=None):
    """Build a POST request with the given data dict."""
    request = factory.post("/admin/", data=data or {})
    request.META["SERVER_NAME"] = "testserver"
    return request


def _confirmed_post(factory, extra=None):
    """Build a confirmed export POST request with optional extra fields."""
    data = {"action": "export_data", "export_confirm": "1", "export_format": "xlsx"}
    if extra:
        data.update(extra)
    return _make_post_request(factory, data)


# ---------------------------------------------------------------------------
# TimestampedAdminMixin
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# DataExportMixin tests
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# DataExportMixin with custom export_fields / export_filename
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# DataExportMixin — DateField and JSONField serialization
# ---------------------------------------------------------------------------
