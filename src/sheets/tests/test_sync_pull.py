from unittest.mock import patch

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from projects.models import Project, Semester
from sheets.models import SheetLink, SheetsAccount, SyncLog


class PullFromSheetTests(TestCase):
    def setUp(self):
        self.account = SheetsAccount.objects.create(
            email="test@test.iam.gserviceaccount.com",
            service_account_json='{"type": "service_account"}',
        )
        ct = ContentType.objects.get_for_model(Project)
        self.link = SheetLink.objects.create(
            name="Test Projects",
            account=self.account,
            spreadsheet_id="test-spreadsheet",
            sheet_name="Sheet1",
            content_type=ct,
            column_mapping={
                "Class": "class_code",
                "Team#": "team_number",
                "TeamName": "team_name",
                "Project Title": "project_title",
                "Organization": "organization",
                "Industry": "industry",
                "Abstract": "abstract",
                "Student Names": "student_names",
            },
            fk_config={
                "semester": {"create_if_missing": True, "defaults": {"is_published": True}},
            },
            lookup_fields=["team_number", "project_title"],
            row_transform_hook="projects.services.hooks.resolve_project_row",
        )
        # Add Year-Semester to column_mapping for the hook
        self.link.column_mapping["Year-Semester"] = "__skip__"
        self.link.save()

    @patch("sheets.services.sync.fetch_raw_values")
    def test_pull_creates_projects(self, mock_fetch):
        mock_fetch.return_value = [
            [
                "Year-Semester",
                "Class",
                "Team#",
                "TeamName",
                "Project Title",
                "Organization",
                "Industry",
                "Abstract",
                "Student Names",
            ],
            ["2025-2 Fall", "CSE", "1", "Alpha", "Test Project", "Org1", "Tech", "An abstract", "Alice, Bob"],
            ["2025-2 Fall", "CSE", "2", "Beta", "Another Project", "Org2", "Health", "Another abstract", "Charlie"],
        ]

        from sheets.services.sync import pull_from_sheet

        log = pull_from_sheet(self.link)

        self.assertEqual(log.status, SyncLog.Status.SUCCESS)
        self.assertEqual(log.rows_created, 2)
        self.assertEqual(log.rows_failed, 0)
        self.assertEqual(Project.objects.count(), 2)
        self.assertTrue(Semester.objects.filter(year=2025, season=2).exists())

    @patch("sheets.services.sync.fetch_raw_values")
    def test_pull_updates_existing(self, mock_fetch):
        semester = Semester.objects.create(year=2025, season=2, is_published=True)
        Project.objects.create(
            semester=semester,
            team_number="1",
            project_title="Test Project",
            organization="Old Org",
        )

        mock_fetch.return_value = [
            [
                "Year-Semester",
                "Class",
                "Team#",
                "TeamName",
                "Project Title",
                "Organization",
                "Industry",
                "Abstract",
                "Student Names",
            ],
            ["2025-2 Fall", "CSE", "1", "Alpha", "Test Project", "New Org", "Tech", "Updated", "Alice"],
        ]

        from sheets.services.sync import pull_from_sheet

        log = pull_from_sheet(self.link)

        self.assertEqual(log.rows_updated, 1)
        self.assertEqual(log.rows_created, 0)
        project = Project.objects.get(team_number="1", project_title="Test Project")
        self.assertEqual(project.organization, "New Org")

    @patch("sheets.services.sync.fetch_raw_values")
    def test_pull_empty_sheet(self, mock_fetch):
        mock_fetch.return_value = []

        from sheets.services.sync import pull_from_sheet

        log = pull_from_sheet(self.link)

        self.assertEqual(log.status, SyncLog.Status.SUCCESS)
        self.assertEqual(log.rows_processed, 0)
