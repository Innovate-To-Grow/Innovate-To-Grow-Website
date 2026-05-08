from django.test import TestCase

from projects.models import Semester
from projects.services.hooks import resolve_project_row


class ResolveProjectRowTest(TestCase):
    def test_valid_year_semester_resolves(self):
        raw_row = {"Year-Semester": "2025-2 Fall", "project_title": "Test"}
        result = resolve_project_row(raw_row, sheet_link=None)

        self.assertIsNotNone(result)
        self.assertIsInstance(result["semester"], Semester)
        self.assertEqual(result["semester"].year, 2025)
        self.assertEqual(result["semester"].season, 2)
        self.assertNotIn("Year-Semester", result)

    def test_publishes_semester(self):
        raw_row = {"Year-Semester": "2025-1 Spring", "project_title": "Test"}
        result = resolve_project_row(raw_row, sheet_link=None)

        self.assertTrue(result["semester"].is_published)

    def test_reuses_existing_semester(self):
        Semester.objects.create(year=2024, season=1, is_published=False)
        raw_row = {"Year-Semester": "2024-1 Spring", "data": "value"}
        result = resolve_project_row(raw_row, sheet_link=None)

        self.assertEqual(Semester.objects.filter(year=2024, season=1).count(), 1)
        self.assertTrue(result["semester"].is_published)

    def test_empty_year_semester_returns_none(self):
        raw_row = {"Year-Semester": "", "project_title": "Test"}
        self.assertIsNone(resolve_project_row(raw_row, sheet_link=None))

    def test_missing_year_semester_returns_none(self):
        raw_row = {"project_title": "Test"}
        self.assertIsNone(resolve_project_row(raw_row, sheet_link=None))

    def test_invalid_format_returns_none(self):
        raw_row = {"Year-Semester": "not-valid", "project_title": "Test"}
        self.assertIsNone(resolve_project_row(raw_row, sheet_link=None))

    def test_preserves_other_fields(self):
        raw_row = {"Year-Semester": "2025-2 Fall", "team_name": "Alpha", "industry": "Tech"}
        result = resolve_project_row(raw_row, sheet_link=None)

        self.assertEqual(result["team_name"], "Alpha")
        self.assertEqual(result["industry"], "Tech")

    def test_whitespace_trimmed(self):
        raw_row = {"Year-Semester": "  2025-2 Fall  ", "data": "value"}
        result = resolve_project_row(raw_row, sheet_link=None)

        self.assertIsNotNone(result)
        self.assertEqual(result["semester"].year, 2025)
