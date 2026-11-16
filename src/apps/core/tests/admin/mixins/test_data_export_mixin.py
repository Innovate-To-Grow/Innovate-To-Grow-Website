from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.cms.models import NewsArticle
from apps.core.admin.mixins import (
    DataExportMixin,
    ExcelExportMixin,
)
from apps.core.tests.admin.mixins.test_mixins import (
    XLSX_CONTENT_TYPE,
    User,
    _confirmed_post,
    _DataExportAdmin,
    _load_xlsx,
    _make_article,
    _make_post_request,
)


class _DataExportMixinCase(TestCase):
    def setUp(self):
        self.admin = _DataExportAdmin()
        self.factory = RequestFactory()
        self.request = self.factory.get("/admin/")


class DataExportMixinTest(_DataExportMixinCase):
    def test_actions_include_export_data(self):
        actions = self.admin.get_actions(self.request)
        self.assertIn("export_data", actions)

    def test_action_tuple_uses_unbound_method(self):
        actions = self.admin.get_actions(self.request)
        func = actions["export_data"][0]
        self.assertFalse(hasattr(func, "__self__"), "Action func should be unbound to avoid double-self bug")

    def test_excel_export_mixin_alias(self):
        self.assertIs(ExcelExportMixin, DataExportMixin)

    def test_default_fields_returns_all_model_fields(self):
        fields = self.admin.get_export_fields()
        field_names = [name for name, _label in fields]
        model_field_names = [f.name for f in NewsArticle._meta.fields]
        self.assertEqual(field_names, model_field_names)

    def test_default_fields_returns_verbose_name_labels(self):
        fields = self.admin.get_export_fields()
        field_dict = dict(fields)
        self.assertEqual(field_dict["published_at"], "Published At")
        self.assertEqual(field_dict["source_url"], "Source Url")

    def test_backward_compat_get_excel_export_fields(self):
        self.assertEqual(self.admin.get_excel_export_fields(), self.admin.get_export_fields())

    def test_value_none_returns_empty_string(self):
        article = _make_article(source_guid="val-none", author="")
        self.assertEqual(self.admin.get_export_value(article, "raw_payload"), "")

    def test_value_datetime_formatted(self):
        dt = timezone.now()
        article = _make_article(source_guid="val-dt", published_at=dt)
        result = self.admin.get_export_value(article, "published_at")
        self.assertEqual(result, dt.strftime("%Y-%m-%d %H:%M:%S"))

    def test_value_uuid_returned_as_string(self):
        article = _make_article(source_guid="val-uuid")
        result = self.admin.get_export_value(article, "id")
        self.assertEqual(result, str(article.id))

    def test_value_string_returned_as_is(self):
        article = _make_article(source_guid="val-str", title="Hello")
        self.assertEqual(self.admin.get_export_value(article, "title"), "Hello")

    def test_value_date_formatted(self):
        from datetime import date

        class _FakeDateObj:
            date_field = date(2025, 3, 15)

        result = self.admin.get_export_value(_FakeDateObj(), "date_field")
        self.assertEqual(result, "2025-03-15")

    def test_value_list_serialized_as_json(self):
        article = _make_article(source_guid="val-list")
        article.raw_payload = ""
        article._test_list = [{"q": "Color?", "a": "Blue"}]
        result = self.admin.get_export_value(article, "_test_list")
        self.assertEqual(result, '[{"q": "Color?", "a": "Blue"}]')

    def test_value_dict_serialized_as_json(self):
        article = _make_article(source_guid="val-dict")
        article._test_dict = {"key": "value", "num": 42}
        result = self.admin.get_export_value(article, "_test_dict")
        self.assertIn('"key": "value"', result)
        self.assertIn('"num": 42', result)

    def test_value_bool_returns_yes_no(self):
        class _FakeBoolObj:
            active = True
            deleted = False

        self.assertEqual(self.admin.get_export_value(_FakeBoolObj(), "active"), "Yes")
        self.assertEqual(self.admin.get_export_value(_FakeBoolObj(), "deleted"), "No")

    def test_backward_compat_get_excel_export_value(self):
        article = _make_article(source_guid="compat-val")
        self.assertEqual(
            self.admin.get_excel_export_value(article, "title"),
            self.admin.get_export_value(article, "title"),
        )

    def test_initial_post_renders_column_selection_template(self):
        article = _make_article(source_guid="tmpl-1")
        qs = NewsArticle.objects.filter(pk=article.pk)

        request = _make_post_request(
            self.factory,
            {
                "action": "export_data",
                "_selected_action": [str(article.pk)],
            },
        )
        request.user = User.objects.create_user(email="tmpl@example.com", password="StrongPass123!", is_staff=True)
        response = self.admin.export_data(request, qs)

        self.assertEqual(response.template_name, "admin/core/export_columns.html")
        self.assertIn(str(article.pk), response.context_data["pks"])
        self.assertGreater(len(response.context_data["available_fields"]), 0)
        self.assertEqual(response.context_data["default_filename"], "newsarticle")
        self.assertEqual(len(response.context_data["formats"]), 2)

    def test_xlsx_confirmed_post_returns_xlsx(self):
        a1 = _make_article(source_guid="xlsx-1", title="First Article")
        a2 = _make_article(source_guid="xlsx-2", title="Second Article")
        qs = NewsArticle.objects.filter(pk__in=[a1.pk, a2.pk])

        request = _confirmed_post(self.factory)
        response = self.admin.export_data(request, qs)

        self.assertEqual(response["Content-Type"], XLSX_CONTENT_TYPE)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn(".xlsx", response["Content-Disposition"])

    def test_xlsx_contains_header_and_data_rows(self):
        a1 = _make_article(source_guid="rows-1", title="Alpha")
        a2 = _make_article(source_guid="rows-2", title="Beta")
        qs = NewsArticle.objects.filter(pk__in=[a1.pk, a2.pk]).order_by("title")

        request = _confirmed_post(self.factory)
        response = self.admin.export_data(request, qs)

        wb = _load_xlsx(response.content)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))

        header = rows[0]
        self.assertIn("Title", header)
        self.assertIn("Source", header)

        self.assertEqual(len(rows), 3)  # 1 header + 2 data
        titles = {row[header.index("Title")] for row in rows[1:]}
        self.assertEqual(titles, {"Alpha", "Beta"})
