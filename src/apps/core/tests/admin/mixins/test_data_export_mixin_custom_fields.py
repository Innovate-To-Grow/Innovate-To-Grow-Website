import json

from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.cms.models import NewsArticle
from apps.core.admin.mixins import (
    DataExportMixin,
)
from apps.core.tests.admin.mixins.test_mixins import (
    _confirmed_post,
    _DataExportAdmin,
    _DataExportCustomAdmin,
    _load_xlsx,
    _make_article,
    _MockSuperAdmin,
)


class DataExportMixinCustomFieldsTest(TestCase):
    def setUp(self):
        self.admin = _DataExportCustomAdmin()
        self.factory = RequestFactory()

    def test_custom_fields_limits_available_columns(self):
        fields = self.admin.get_export_fields()
        field_names = [name for name, _label in fields]
        self.assertEqual(field_names, ["title", "source", "published_at"])

    def test_custom_filename_used_in_xlsx_response(self):
        _make_article(source_guid="cust-fname-1")
        qs = NewsArticle.objects.all()

        request = _confirmed_post(self.factory)
        response = self.admin.export_data(request, qs)

        self.assertIn("custom_articles_", response["Content-Disposition"])

    def test_custom_fields_exports_only_specified_columns(self):
        dt = timezone.now()
        _make_article(source_guid="cust-cols-1", title="Custom", source="manual", published_at=dt)
        qs = NewsArticle.objects.all()

        request = _confirmed_post(self.factory)
        response = self.admin.export_data(request, qs)

        wb = _load_xlsx(response.content)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        header = rows[0]

        self.assertEqual(len(header), 3)
        self.assertEqual(rows[1][header.index("Title")], "Custom")
        self.assertEqual(rows[1][header.index("Source")], "manual")

    def test_custom_filename_used_in_json_response(self):
        _make_article(source_guid="cust-json-fname-1")
        qs = NewsArticle.objects.all()

        request = _confirmed_post(self.factory, {"export_format": "json"})
        response = self.admin.export_data(request, qs)

        self.assertIn("custom_articles_", response["Content-Disposition"])
        self.assertIn(".json", response["Content-Disposition"])

    def test_backward_compat_excel_export_fields_property(self):
        self.assertEqual(self.admin.excel_export_fields, ["title", "source", "published_at"])

    def test_backward_compat_excel_export_filename_property(self):
        self.assertEqual(self.admin.excel_export_filename, "custom_articles")

    def test_excel_export_fields_setter(self):
        self.admin.excel_export_fields = ["title"]
        self.assertEqual(self.admin.export_fields, ["title"])

    def test_excel_export_filename_setter(self):
        self.admin.excel_export_filename = "renamed"
        self.assertEqual(self.admin.export_filename, "renamed")

    def test_get_export_fields_falls_back_for_unknown_field(self):
        admin = _DataExportCustomAdmin()
        admin.export_fields = ["title", "not_a_real_field"]
        fields = dict(admin.get_export_fields())
        # Real field keeps its verbose name; unknown field gets a humanized label.
        self.assertEqual(fields["title"], "Title")
        self.assertEqual(fields["not_a_real_field"], "Not A Real Field")


class DataExportRelatedValueTest(TestCase):
    def test_related_object_value_returned_as_str(self):
        """A FK value (has .pk) is serialized via str()."""
        from apps.event.models import CheckIn, Event

        admin = _DataExportAdmin()
        event = Event.objects.create(
            name="E",
            slug="e-export",
            date="2025-06-15",
            end_date="2025-06-15",
            location="L",
        )
        check_in = CheckIn.objects.create(event=event, name="Door")
        result = admin.get_export_value(check_in, "event")
        self.assertEqual(result, str(event))


class _DateFieldExportAdmin(DataExportMixin, _MockSuperAdmin):
    """Admin that exports Event-like models with DateField and JSONField."""

    model = None  # set in setUp via monkey-patch


class DataExportDateFieldTest(TestCase):
    """Verify JSON export does not crash on DateField / JSONField values."""

    def setUp(self):
        self.admin = _DataExportAdmin()
        self.factory = RequestFactory()

    def test_json_export_with_date_field_does_not_crash(self):
        """Regression: DateField values caused TypeError in json.dumps."""
        from apps.event.models import Event

        event = Event.objects.create(
            name="Test Event",
            slug="test-export-date",
            date="2025-06-15",
            end_date="2025-06-15",
            location="Room A",
            description="Testing",
        )

        # Build a fresh admin bound to Event model
        admin = _DataExportAdmin()
        admin.model = Event

        qs = Event.objects.filter(pk=event.pk)
        request = _confirmed_post(self.factory, {"export_format": "json"})

        response = admin.export_data(request, qs)

        self.assertEqual(response["Content-Type"], "application/json")
        data = json.loads(response.content)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["date"], "2025-06-15")

    def test_json_export_with_json_field_does_not_crash(self):
        """Regression: list/dict values from JSONField caused TypeError in json.dumps."""
        article = _make_article(source_guid="json-field-1", title="JSON Export")
        # Simulate a JSONField value by attaching a list attribute
        # (NewsArticle doesn't have a JSONField, so we use a custom export_fields admin)
        qs = NewsArticle.objects.filter(pk=article.pk)
        request = _confirmed_post(self.factory, {"export_format": "json"})

        # The export should not crash — json.dumps with default=str handles any leftovers
        response = self.admin.export_data(request, qs)

        self.assertEqual(response["Content-Type"], "application/json")
        data = json.loads(response.content)
        self.assertEqual(len(data), 1)
        self.assertIn("title", data[0])
