import uuid
from unittest.mock import patch

from django.test import TestCase

from apps.core.services.db_tools.safe_orm import (
    cascade_summary,
    collect_cascade_impact,
    json_safe,
)
from apps.projects.models import Project, Semester


class CascadeTests(TestCase):
    def setUp(self):
        self.sem = Semester.objects.create(year=2030, season=1)

    def test_zero_cascade(self):
        self.assertEqual(collect_cascade_impact(self.sem)["total"], 0)

    def test_cascade_with_children(self):
        Project.objects.create(semester=self.sem, project_title="Child")
        result = collect_cascade_impact(self.sem)
        self.assertGreaterEqual(result["total"], 1)
        self.assertTrue(any(item["model"] == "projects.Project" for item in result["related"]))

    def test_cascade_counts_sibling_rows_of_same_class(self):
        sib1 = Semester.objects.create(year=2031, season=1)
        sib2 = Semester.objects.create(year=2032, season=1)

        def fake_collect(collector, objs, *args, **kwargs):
            collector.data = {Semester: {self.sem, sib1, sib2}}

        with patch(
            "apps.core.services.db_tools.safe_orm.cascade.Collector.collect",
            autospec=True,
            side_effect=fake_collect,
        ):
            result = collect_cascade_impact(self.sem)
        self.assertEqual(result["total"], 2)  # the target itself is excluded

    def test_cascade_handles_collector_failure(self):
        with patch(
            "apps.core.services.db_tools.safe_orm.cascade.Collector.collect",
            side_effect=RuntimeError("boom"),
        ):
            result = collect_cascade_impact(self.sem)
        self.assertEqual(result["total"], 0)
        self.assertIn("error", result)

    def test_cascade_summary(self):
        self.assertEqual(cascade_summary("base", {"total": 0}), "base")
        with_total = cascade_summary("base", {"total": 2, "related": [{"model": "X", "count": 2}]})
        self.assertIn("Cascade will also remove", with_total)
        many = cascade_summary(
            None,
            {"total": 9, "related": [{"model": m, "count": 1} for m in ("A", "B", "C", "D")]},
        )
        self.assertIn("...", many)


class JsonTests(TestCase):
    def test_json_safe_roundtrips_uuid(self):
        value = json_safe({"id": uuid.uuid4()})
        self.assertIsInstance(value["id"], str)
