from django.test import TestCase

from apps.system_intelligence.services.query_tools.tool_modules.custom.query import (
    apply_filters,
    apply_ordering,
    run_custom_query,
    serialize_custom_rows,
)


class RunCustomQueryTest(TestCase):
    def _make_semester(self, **kw):
        from apps.projects.models import Semester

        defaults = {"year": 2025, "season": 1, "is_published": True, "label": "Spring 2025"}
        defaults.update(kw)
        return Semester.objects.create(**defaults)

    def test_unknown_model(self):
        result = run_custom_query({"model": "Unicorn"})
        self.assertIn("Unknown model 'Unicorn'", result)

    def test_count_only(self):
        self._make_semester()
        self._make_semester(year=2024)
        result = run_custom_query({"model": "Semester", "count_only": True})
        self.assertEqual(result, "Count: 2")

    def test_filter_error_for_disallowed_field(self):
        result = run_custom_query({"model": "Semester", "filters": {"secret": 1}})
        self.assertIn("Filter error: field 'secret' is not allowed", result)

    def test_ordering_error_for_disallowed_field(self):
        result = run_custom_query({"model": "Semester", "ordering": "secret"})
        self.assertIn("Ordering error: field 'secret' is not allowed", result)

    def test_explicit_fields(self):
        self._make_semester()
        result = run_custom_query({"model": "Semester", "fields": ["year", "label"], "filters": {"year": 2025}})
        self.assertIn("2025", result)
        self.assertIn('"label"', result)

    def test_invalid_explicit_fields(self):
        self._make_semester()
        result = run_custom_query({"model": "Semester", "fields": ["nope"]})
        self.assertIn("field 'nope' is not allowed", result)

    def test_default_fields_serialization(self):
        self._make_semester()
        result = run_custom_query({"model": "Semester", "ordering": ["-year"]})
        self.assertIn("result(s) from Semester", result)
        self.assertIn("2025", result)

    def test_apply_filters_with_non_dict_returns_qs(self):
        from apps.projects.models import Semester

        qs = Semester.objects.all()
        self.assertIs(apply_filters(qs, "Semester", []), qs)

    def test_apply_filters_runtime_error(self):
        from apps.projects.models import Semester

        qs = Semester.objects.all()
        # 'year' is an allowed integer field; a non-numeric value raises during
        # .filter() value coercion, exercising the `Filter error: {exc}` branch.
        result = apply_filters(qs, "Semester", {"year": "not-an-int"})
        self.assertIsInstance(result, str)
        self.assertTrue(result.startswith("Filter error:"))

    def test_apply_ordering_string_normalized(self):
        from apps.projects.models import Semester

        self._make_semester()
        qs = apply_ordering(Semester.objects.all(), "Semester", "-year")
        self.assertTrue(hasattr(qs, "order_by"))
        list(qs)  # force evaluation

    def test_apply_ordering_runtime_error(self):
        from unittest.mock import MagicMock

        from apps.projects.models import Semester

        qs = Semester.objects.all()
        broken = MagicMock(wraps=qs)
        broken.order_by.side_effect = RuntimeError("bad ordering")
        result = apply_ordering(broken, "Semester", "year")
        self.assertEqual(result, "Ordering error: bad ordering")

    def test_serialize_custom_rows_respects_limit(self):
        from apps.projects.models import Semester

        for y in range(2020, 2025):
            self._make_semester(year=y)
        result = serialize_custom_rows(Semester.objects.all(), "Semester", {"limit": 2, "fields": ["year"]})
        self.assertIn("Showing 2 of 5", result)
