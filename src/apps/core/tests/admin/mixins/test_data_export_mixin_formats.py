import json

from django.http import QueryDict

from apps.cms.models import NewsArticle
from apps.core.tests.admin.mixins.test_data_export_mixin import _DataExportMixinCase
from apps.core.tests.admin.mixins.test_mixins import _confirmed_post, _load_xlsx, _make_article, _make_post_request


class DataExportMixinTest(_DataExportMixinCase):
    def test_xlsx_header_has_blue_fill(self):
        _make_article(source_guid="style-1")
        qs = NewsArticle.objects.all()

        request = _confirmed_post(self.factory)
        response = self.admin.export_data(request, qs)

        wb = _load_xlsx(response.content)
        ws = wb.active
        header_cell = ws.cell(row=1, column=1)
        self.assertEqual(header_cell.fill.start_color.rgb, "004472C4")

    def test_selected_columns_limits_exported_fields(self):
        article = _make_article(source_guid="sel-1", title="Selected", source="rss")
        qs = NewsArticle.objects.filter(pk=article.pk)

        request = _make_post_request(self.factory, QueryDict(mutable=True))
        request.POST = QueryDict(mutable=True)
        request.POST["action"] = "export_data"
        request.POST["export_confirm"] = "1"
        request.POST["export_format"] = "xlsx"
        request.POST.setlist("export_fields", ["title", "source"])

        response = self.admin.export_data(request, qs)

        wb = _load_xlsx(response.content)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        header = rows[0]

        self.assertEqual(len(header), 2)
        self.assertEqual(header, ("Title", "Source"))
        self.assertEqual(rows[1], ("Selected", "rss"))

    def test_empty_selection_exports_all_columns(self):
        _make_article(source_guid="empty-sel-1")
        qs = NewsArticle.objects.all()

        request = _confirmed_post(self.factory)
        response = self.admin.export_data(request, qs)

        wb = _load_xlsx(response.content)
        ws = wb.active
        header = next(ws.iter_rows(values_only=True))
        model_field_count = len(NewsArticle._meta.fields)
        self.assertEqual(len(header), model_field_count)

    def test_default_filename_uses_model_name(self):
        _make_article(source_guid="fname-1")
        qs = NewsArticle.objects.all()

        request = _confirmed_post(self.factory)
        response = self.admin.export_data(request, qs)

        self.assertIn("newsarticle_", response["Content-Disposition"])

    def test_user_provided_filename_used_in_response(self):
        _make_article(source_guid="ufname-1")
        qs = NewsArticle.objects.all()

        request = _confirmed_post(self.factory, {"export_filename": "my_custom_report"})
        response = self.admin.export_data(request, qs)

        self.assertIn("my_custom_report_", response["Content-Disposition"])
        self.assertNotIn("newsarticle_", response["Content-Disposition"])

    def test_blank_user_filename_falls_back_to_default(self):
        _make_article(source_guid="bfname-1")
        qs = NewsArticle.objects.all()

        request = _confirmed_post(self.factory, {"export_filename": "   "})
        response = self.admin.export_data(request, qs)

        self.assertIn("newsarticle_", response["Content-Disposition"])

    def test_json_format_returns_json_response(self):
        a1 = _make_article(source_guid="json-1", title="First")
        a2 = _make_article(source_guid="json-2", title="Second")
        qs = NewsArticle.objects.filter(pk__in=[a1.pk, a2.pk])

        request = _confirmed_post(self.factory, {"export_format": "json"})
        response = self.admin.export_data(request, qs)

        self.assertEqual(response["Content-Type"], "application/json")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn(".json", response["Content-Disposition"])

        data = json.loads(response.content)
        self.assertEqual(len(data), 2)
        titles = {item["title"] for item in data}
        self.assertEqual(titles, {"First", "Second"})

    def test_json_format_respects_column_selection(self):
        _make_article(source_guid="json-sel-1", title="Filtered", source="api")
        qs = NewsArticle.objects.all()

        request = _make_post_request(self.factory, QueryDict(mutable=True))
        request.POST = QueryDict(mutable=True)
        request.POST["action"] = "export_data"
        request.POST["export_confirm"] = "1"
        request.POST["export_format"] = "json"
        request.POST.setlist("export_fields", ["title", "source"])

        response = self.admin.export_data(request, qs)

        data = json.loads(response.content)
        self.assertEqual(len(data), 1)
        self.assertEqual(set(data[0].keys()), {"title", "source"})

    def test_json_format_uses_custom_filename(self):
        _make_article(source_guid="json-fname-1")
        qs = NewsArticle.objects.all()

        request = _confirmed_post(self.factory, {"export_format": "json", "export_filename": "my_report"})
        response = self.admin.export_data(request, qs)

        self.assertIn("my_report_", response["Content-Disposition"])
        self.assertIn(".json", response["Content-Disposition"])

    def test_json_default_exports_all_columns(self):
        _make_article(source_guid="json-all-1")
        qs = NewsArticle.objects.all()

        request = _confirmed_post(self.factory, {"export_format": "json"})
        response = self.admin.export_data(request, qs)

        data = json.loads(response.content)
        model_field_names = {f.name for f in NewsArticle._meta.fields}
        self.assertEqual(set(data[0].keys()), model_field_names)
