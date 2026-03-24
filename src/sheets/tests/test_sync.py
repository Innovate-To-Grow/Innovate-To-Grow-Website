from unittest.mock import patch

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from projects.models import Project, Semester
from sheets.models import SheetLink, SheetsAccount, SyncLog
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


class PushToSheetTests(TestCase):
    def setUp(self):
        self.account = SheetsAccount.objects.create(
            email="test@test.iam.gserviceaccount.com",
            service_account_json='{"type": "service_account"}',
        )
        ct = ContentType.objects.get_for_model(Project)
        self.link = SheetLink.objects.create(
            name="Test Push",
            account=self.account,
            spreadsheet_id="test-spreadsheet",
            sheet_name="Sheet1",
            content_type=ct,
            column_mapping={
                "Year": "semester__year",
                "Season": "semester__season",
                "Class": "class_code",
                "Team#": "team_number",
                "Project Title": "project_title",
            },
            sync_direction="push",
        )

    @patch("sheets.services.client.write_values")
    @patch("sheets.services.client.clear_range")
    def test_push_writes_all_projects(self, mock_clear, mock_write):
        semester = Semester.objects.create(year=2025, season=2, is_published=True)
        Project.objects.create(semester=semester, team_number="1", project_title="P1", class_code="CSE")
        Project.objects.create(semester=semester, team_number="2", project_title="P2", class_code="CAP")

        from sheets.services.sync import push_to_sheet

        log = push_to_sheet(self.link)

        self.assertEqual(log.status, SyncLog.Status.SUCCESS)
        self.assertEqual(log.rows_created, 2)  # rows_created = rows written in push context

        mock_clear.assert_called_once()
        mock_write.assert_called_once()

        # Check the written values
        written_values = mock_write.call_args[0][3]  # 4th positional arg
        self.assertEqual(written_values[0], ["Year", "Season", "Class", "Team#", "Project Title"])  # headers
        self.assertEqual(len(written_values), 3)  # header + 2 data rows
