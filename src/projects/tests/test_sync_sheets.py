from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from projects.models import Project, Semester
from projects.services.sync_sheets import _parse_year_semester, sync_from_sheet


class ParseYearSemesterTests(TestCase):
    def test_valid_fall(self):
        self.assertEqual(_parse_year_semester("2025-2 Fall"), (2025, 2))

    def test_valid_spring(self):
        self.assertEqual(_parse_year_semester("2024-1 Spring"), (2024, 1))

    def test_empty_string(self):
        self.assertIsNone(_parse_year_semester(""))

    def test_none(self):
        self.assertIsNone(_parse_year_semester(None))

    def test_invalid_format(self):
        self.assertIsNone(_parse_year_semester("Fall 2025"))

    def test_missing_season_label(self):
        # Trailing space with no label — regex requires space so this matches
        self.assertIsNone(_parse_year_semester("2025-2 "))

    def test_no_space_after_number(self):
        self.assertIsNone(_parse_year_semester("2025-2"))


CURRENT_EVENT_ROWS = [
    ["Track", "Order", "Year-Semester", "Class", "Team#", "TeamName",
     "Project Title", "Organization", "Industry", "Abstract", "Student Names", "NameTitle"],
    ["1", "1", "2025-2 Fall", "ENGR 120", "T01", "Alpha",
     "Project Alpha", "Acme Corp", "Tech", "An abstract", "Alice, Bob", "Dr. Smith"],
    ["1", "2", "2025-2 Fall", "ENGR 120", "T02", "Beta",
     "Project Beta", "Beta Inc", "Health", "Another abstract", "Charlie", ""],
    ["2", "1", "2025-1 Spring", "ME 150", "T03", "Gamma",
     "Project Gamma", "Gamma LLC", "Energy", "Third abstract", "Dave, Eve", ""],
]

PAST_PROJECTS_ROWS = [
    ["Year-Semester", "Class", "Team#", "TeamName", "Project Title",
     "Organization", "Industry", "Abstract", "Student Names"],
    ["2023-2 Fall", "ENGR 120", "T01", "Delta",
     "Project Delta", "Delta Co", "Finance", "Past abstract", "Frank"],
    ["2023-1 Spring", "ME 150", "T02", "Epsilon",
     "Project Epsilon", "Epsilon Ltd", "Bio", "Another past", "Grace"],
]


def _mock_fetch(spreadsheet_id, range_ref):
    """Return test data based on spreadsheet_id."""
    if spreadsheet_id == "current-sheet":
        return CURRENT_EVENT_ROWS
    elif spreadsheet_id == "past-sheet":
        return PAST_PROJECTS_ROWS
    return []


class SyncFromSheetCurrentEventTests(TestCase):
    def setUp(self):
        cache.clear()

    @patch("projects.services.sync_sheets.fetch_raw_values", side_effect=_mock_fetch)
    def test_creates_semesters_and_projects(self, mock_fetch):
        stats = sync_from_sheet("current-sheet", "Sheet1!A:L", "current-event")

        self.assertEqual(stats["semesters_created"], 2)
        self.assertEqual(stats["projects_created"], 3)
        self.assertEqual(stats["projects_updated"], 0)
        self.assertEqual(stats["rows_skipped"], 0)

        self.assertEqual(Semester.objects.count(), 2)
        self.assertEqual(Project.objects.count(), 3)

        # Check project fields
        alpha = Project.objects.get(project_title="Project Alpha")
        self.assertEqual(alpha.track, 1)
        self.assertEqual(alpha.presentation_order, 1)
        self.assertEqual(alpha.class_code, "ENGR 120")
        self.assertEqual(alpha.team_number, "T01")
        self.assertEqual(alpha.organization, "Acme Corp")
        self.assertEqual(alpha.abstract, "An abstract")

    @patch("projects.services.sync_sheets.fetch_raw_values", side_effect=_mock_fetch)
    def test_semester_filter(self, mock_fetch):
        stats = sync_from_sheet("current-sheet", "Sheet1!A:L", "current-event", semester_filter="2025-2 Fall")

        self.assertEqual(stats["projects_created"], 2)  # Only Fall 2025 rows
        self.assertEqual(stats["rows_skipped"], 1)  # Spring row skipped

    @patch("projects.services.sync_sheets.fetch_raw_values", side_effect=_mock_fetch)
    def test_resync_updates_existing(self, mock_fetch):
        # First sync
        sync_from_sheet("current-sheet", "Sheet1!A:L", "current-event")
        self.assertEqual(Project.objects.count(), 3)

        # Second sync — same data, should update not create
        stats = sync_from_sheet("current-sheet", "Sheet1!A:L", "current-event")
        self.assertEqual(stats["projects_created"], 0)
        self.assertEqual(stats["projects_updated"], 3)
        self.assertEqual(Project.objects.count(), 3)

    @patch("projects.services.sync_sheets.fetch_raw_values", side_effect=_mock_fetch)
    def test_semesters_auto_published(self, mock_fetch):
        sync_from_sheet("current-sheet", "Sheet1!A:L", "current-event")

        for sem in Semester.objects.all():
            self.assertTrue(sem.is_published)


class SyncFromSheetPastProjectsTests(TestCase):
    def setUp(self):
        cache.clear()

    @patch("projects.services.sync_sheets.fetch_raw_values", side_effect=_mock_fetch)
    def test_creates_past_projects(self, mock_fetch):
        stats = sync_from_sheet("past-sheet", "Sheet1!A:I", "past-projects")

        self.assertEqual(stats["semesters_created"], 2)
        self.assertEqual(stats["projects_created"], 2)

        delta = Project.objects.get(project_title="Project Delta")
        self.assertIsNone(delta.track)
        self.assertIsNone(delta.presentation_order)
        self.assertEqual(delta.team_name, "Delta")
        self.assertEqual(delta.industry, "Finance")


class SyncSkipsInvalidRowsTests(TestCase):
    def setUp(self):
        cache.clear()

    @patch("projects.services.sync_sheets.fetch_raw_values")
    def test_skips_rows_without_title(self, mock_fetch):
        mock_fetch.return_value = [
            ["Year-Semester", "Class", "Team#", "TeamName", "Project Title",
             "Organization", "Industry", "Abstract", "Student Names"],
            ["2025-2 Fall", "ENGR 120", "T01", "Alpha", "",
             "Acme", "Tech", "Abstract", "Alice"],
        ]
        stats = sync_from_sheet("x", "A:I", "past-projects")
        self.assertEqual(stats["rows_skipped"], 1)
        self.assertEqual(stats["projects_created"], 0)

    @patch("projects.services.sync_sheets.fetch_raw_values")
    def test_skips_rows_with_invalid_semester(self, mock_fetch):
        mock_fetch.return_value = [
            ["Year-Semester", "Class", "Team#", "TeamName", "Project Title",
             "Organization", "Industry", "Abstract", "Student Names"],
            ["bad-value", "ENGR 120", "T01", "Alpha", "Project X",
             "Acme", "Tech", "Abstract", "Alice"],
        ]
        stats = sync_from_sheet("x", "A:I", "past-projects")
        self.assertEqual(stats["rows_skipped"], 1)
        self.assertEqual(stats["projects_created"], 0)

    @patch("projects.services.sync_sheets.fetch_raw_values")
    def test_empty_sheet(self, mock_fetch):
        mock_fetch.return_value = []
        stats = sync_from_sheet("x", "A:I", "past-projects")
        self.assertEqual(stats["projects_created"], 0)
        self.assertEqual(stats["rows_skipped"], 0)


class SyncCacheClearingTests(TestCase):
    def setUp(self):
        cache.clear()

    @patch("projects.services.sync_sheets.fetch_raw_values", side_effect=_mock_fetch)
    def test_clears_project_caches(self, mock_fetch):
        cache.set("projects:current", {"test": True})
        cache.set("projects:past-all", {"test": True})

        sync_from_sheet("current-sheet", "Sheet1!A:L", "current-event")

        self.assertIsNone(cache.get("projects:current"))
        self.assertIsNone(cache.get("projects:past-all"))
