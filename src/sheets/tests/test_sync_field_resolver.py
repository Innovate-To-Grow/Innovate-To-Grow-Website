from django.test import TestCase

from projects.models import Project, Semester
from sheets.services.field_resolver import coerce_field_value, group_fk_columns, serialize_field_value


class FieldResolverTests(TestCase):
    def test_group_fk_columns_separates_fk_and_direct(self):
        mapping = {
            "Year": "semester__year",
            "Season": "semester__season",
            "Class": "class_code",
            "Team#": "team_number",
            "Skip Me": "__skip__",
        }
        fk_groups, direct = group_fk_columns(mapping)

        self.assertEqual(fk_groups, {"semester": {"year": "Year", "season": "Season"}})
        self.assertEqual(direct, {"Class": "class_code", "Team#": "team_number"})

    def test_group_fk_columns_no_fks(self):
        mapping = {"A": "field_a", "B": "field_b"}
        fk_groups, direct = group_fk_columns(mapping)
        self.assertEqual(fk_groups, {})
        self.assertEqual(direct, {"A": "field_a", "B": "field_b"})

    def test_coerce_integer_field(self):
        from django.db import models

        field = models.IntegerField()
        self.assertEqual(coerce_field_value(field, "42"), 42)

    def test_coerce_boolean_field(self):
        from django.db import models

        field = models.BooleanField()
        self.assertTrue(coerce_field_value(field, "true"))
        self.assertTrue(coerce_field_value(field, "1"))
        self.assertFalse(coerce_field_value(field, "false"))

    def test_coerce_char_field(self):
        from django.db import models

        field = models.CharField()
        self.assertEqual(coerce_field_value(field, "hello"), "hello")

    def test_serialize_direct_field(self):
        semester = Semester.objects.create(year=2025, season=2, is_published=True)
        self.assertEqual(serialize_field_value(semester, "year"), "2025")

    def test_serialize_fk_field(self):
        semester = Semester.objects.create(year=2025, season=2, is_published=True)
        project = Project.objects.create(
            semester=semester,
            team_number="1",
            project_title="Test Project",
        )
        self.assertEqual(serialize_field_value(project, "semester__year"), "2025")
        self.assertEqual(serialize_field_value(project, "semester__season"), "2")
