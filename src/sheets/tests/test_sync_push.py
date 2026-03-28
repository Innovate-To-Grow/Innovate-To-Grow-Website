from unittest.mock import patch

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from projects.models import Project, Semester
from sheets.models import SheetLink, SheetsAccount, SyncLog


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
