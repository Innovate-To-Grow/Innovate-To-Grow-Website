import io

from django.test import TestCase

from projects.models import Project, Semester
from projects.services.csv_import import ImportResult, _parse_semester, import_projects_from_csv


class ParseSemesterTest(TestCase):
    def test_valid_year_semester(self):
        semester = _parse_semester("2024-2 Fall", publish=False)
        self.assertIsNotNone(semester)
        self.assertEqual(semester.year, 2024)
        self.assertEqual(semester.season, 2)
        self.assertFalse(semester.is_published)

    def test_valid_year_semester_with_publish(self):
        semester = _parse_semester("2023-1 Spring", publish=True)
        self.assertIsNotNone(semester)
        self.assertTrue(semester.is_published)

    def test_publish_updates_existing_unpublished(self):
        Semester.objects.create(year=2022, season=1, is_published=False)
        semester = _parse_semester("2022-1 Spring", publish=True)
        self.assertTrue(semester.is_published)

    def test_invalid_format_returns_none(self):
        self.assertIsNone(_parse_semester("bad data", publish=False))
        self.assertIsNone(_parse_semester("", publish=False))

    def test_get_or_create_reuses_existing(self):
        Semester.objects.create(year=2024, season=1)
        semester = _parse_semester("2024-1 Spring", publish=False)
        self.assertEqual(Semester.objects.filter(year=2024, season=1).count(), 1)
        self.assertEqual(semester.year, 2024)


class ImportProjectsFromCSVTest(TestCase):
    def _make_csv(self, rows):
        header = "Year-Semester,ClassCode,Team#,TeamName,ProjectTitle,Organization,Industry,Col7,Abstract,StudentNames"
        lines = [header] + rows
        return io.StringIO("\n".join(lines))

    def test_basic_import(self):
        csv_file = self._make_csv(
            [
                "2024-2 Fall,CSE,101,Alpha,Smart App,TechCorp,Software,,An abstract,Alice Bob",
            ]
        )
        result = import_projects_from_csv(csv_file)
        self.assertEqual(result.created, 1)
        self.assertEqual(result.skipped, 0)
        self.assertEqual(result.errors, [])

        project = Project.objects.first()
        self.assertEqual(project.project_title, "Smart App")
        self.assertEqual(project.class_code, "CSE")
        self.assertEqual(project.team_number, "101")
        self.assertEqual(project.organization, "TechCorp")
        self.assertEqual(project.student_names, "Alice Bob")

    def test_dry_run_does_not_create(self):
        csv_file = self._make_csv(
            [
                "2024-2 Fall,CSE,101,Alpha,Smart App,TechCorp,Software,,Abstract,Names",
            ]
        )
        result = import_projects_from_csv(csv_file, dry_run=True)
        self.assertEqual(result.created, 1)
        self.assertEqual(Project.objects.count(), 0)

    def test_skips_short_rows(self):
        csv_file = self._make_csv(["short,row"])
        result = import_projects_from_csv(csv_file)
        self.assertEqual(result.created, 0)

    def test_skips_empty_year_semester(self):
        csv_file = self._make_csv([",,101,Alpha,Title,Org,Ind,,Abs,Names"])
        result = import_projects_from_csv(csv_file)
        self.assertEqual(result.created, 0)

    def test_error_on_unparseable_year_semester(self):
        csv_file = self._make_csv(["BADVALUE,CSE,101,Alpha,Title,Org,Ind,,Abs,Names"])
        result = import_projects_from_csv(csv_file)
        self.assertEqual(result.created, 0)
        self.assertEqual(len(result.errors), 1)
        self.assertIn("unparseable", result.errors[0])

    def test_error_on_missing_project_title(self):
        csv_file = self._make_csv(["2024-2 Fall,CSE,101,Alpha,,Org,Ind,,Abs,Names"])
        result = import_projects_from_csv(csv_file)
        self.assertEqual(result.created, 0)
        self.assertEqual(len(result.errors), 1)
        self.assertIn("missing project_title", result.errors[0])

    def test_skips_duplicates(self):
        semester = Semester.objects.create(year=2024, season=2)
        Project.objects.create(semester=semester, class_code="CSE", team_number="101", project_title="Existing")

        csv_file = self._make_csv(
            [
                "2024-2 Fall,CSE,101,Alpha,Smart App,TechCorp,Software,,Abstract,Names",
            ]
        )
        result = import_projects_from_csv(csv_file)
        self.assertEqual(result.created, 0)
        self.assertEqual(result.skipped, 1)

    def test_multiple_rows(self):
        csv_file = self._make_csv(
            [
                "2024-2 Fall,CSE,101,Alpha,App One,Org1,Ind1,,Abs1,Names1",
                "2024-2 Fall,CSE,102,Beta,App Two,Org2,Ind2,,Abs2,Names2",
                "2024-1 Spring,CAP,201,Gamma,App Three,Org3,Ind3,,Abs3,Names3",
            ]
        )
        result = import_projects_from_csv(csv_file)
        self.assertEqual(result.created, 3)
        self.assertEqual(Semester.objects.count(), 2)

    def test_publish_flag(self):
        csv_file = self._make_csv(
            [
                "2024-2 Fall,CSE,101,Alpha,Title,Org,Ind,,Abs,Names",
            ]
        )
        import_projects_from_csv(csv_file, publish=True)
        semester = Semester.objects.get(year=2024, season=2)
        self.assertTrue(semester.is_published)

    def test_bytes_file_input(self):
        header = "Year-Semester,ClassCode,Team#,TeamName,ProjectTitle,Organization,Industry,Col7,Abstract,StudentNames"
        row = "2024-2 Fall,CSE,101,Alpha,ByteApp,Org,Ind,,Abs,Names"
        content = f"{header}\n{row}".encode("utf-8-sig")

        csv_file = io.BytesIO(content)
        result = import_projects_from_csv(csv_file)
        self.assertEqual(result.created, 1)


class ImportResultTest(TestCase):
    def test_defaults(self):
        result = ImportResult()
        self.assertEqual(result.created, 0)
        self.assertEqual(result.skipped, 0)
        self.assertEqual(result.errors, [])
