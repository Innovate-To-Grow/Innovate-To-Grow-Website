from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from apps.projects.models import (
    PastProjectsSheetConfig,
    PastProjectSyncLog,
    Project,
    Semester,
)
from apps.projects.services.sheet_sync import SheetSyncError, sync_past_projects


def _record(
    year_semester="2024-2 Fall",
    team="101",
    title="Smart App",
    cls="CSE",
    team_name="Alpha",
    organization="TechCorp",
    industry="Software",
    abstract="An abstract",
    student_names="Alice Bob",
):
    return {
        "Year-Semester": year_semester,
        "Class": cls,
        "Team#": team,
        "Team Name": team_name,
        "Project Title": title,
        "Organization": organization,
        "Industry": industry,
        "Abstract": abstract,
        "Student Names": student_names,
    }


class SyncPastProjectsRunnerTest(TestCase):
    def setUp(self):
        self.config = PastProjectsSheetConfig.objects.create(name="Prod", is_active=True)

    def test_sync_creates_projects_and_publishes_semester(self):
        stats = sync_past_projects(self.config, records=[_record()])

        self.assertEqual(stats.rows_read, 1)
        self.assertEqual(stats.projects_created, 1)
        self.assertEqual(stats.projects_updated, 0)
        self.assertEqual(stats.projects_deleted, 0)
        self.assertEqual(stats.semesters_touched, 1)
        self.assertEqual(stats.rows_skipped, 0)

        project = Project.objects.get()
        self.assertEqual(project.source, Project.Source.SHEET)
        self.assertEqual(project.class_code, "CSE")
        self.assertEqual(project.team_number, "101")
        self.assertEqual(project.project_title, "Smart App")
        self.assertTrue(project.semester.is_published)
        self.assertEqual(project.semester.year, 2024)
        self.assertEqual(project.semester.season, 2)

        log = PastProjectSyncLog.objects.get()
        self.assertEqual(log.status, PastProjectSyncLog.Status.SUCCESS)
        self.assertEqual(log.sync_type, PastProjectSyncLog.SyncType.MANUAL)
        self.assertEqual(log.projects_created, 1)
        self.assertEqual(log.projects_updated, 0)
        self.assertEqual(log.projects_deleted, 0)

    def test_sync_deletes_missing_sheet_rows_only(self):
        semester = Semester.objects.create(year=2024, season=2, is_published=True)
        stale_sheet = Project.objects.create(
            semester=semester,
            project_title="Old sheet row",
            team_number="999",
            source=Project.Source.SHEET,
        )
        manual = Project.objects.create(
            semester=semester,
            project_title="Hand entered",
            team_number="555",
            source=Project.Source.MANUAL,
        )

        stats = sync_past_projects(self.config, records=[_record()])

        # The stale sheet row in the same semester is gone; the manual row survives.
        self.assertFalse(Project.objects.filter(pk=stale_sheet.pk).exists())
        self.assertTrue(Project.objects.filter(pk=manual.pk).exists())
        self.assertEqual(Project.objects.filter(source=Project.Source.SHEET).count(), 1)
        self.assertEqual(stats.projects_created, 1)
        self.assertEqual(stats.projects_deleted, 1)

    def test_existing_sheet_project_keeps_uuid_and_updates_mutable_fields(self):
        sync_past_projects(self.config, records=[_record()])
        project = Project.objects.get()
        original_pk = project.pk

        stats = sync_past_projects(
            self.config,
            records=[
                _record(
                    title="Smarter App",
                    team_name="Beta",
                    organization="New Org",
                    industry="Hardware",
                    abstract="Updated abstract",
                    student_names="Carol Dana",
                )
            ],
        )

        project.refresh_from_db()
        self.assertEqual(project.pk, original_pk)
        self.assertEqual(project.project_title, "Smarter App")
        self.assertEqual(project.team_name, "Beta")
        self.assertEqual(project.organization, "New Org")
        self.assertEqual(project.industry, "Hardware")
        self.assertEqual(project.abstract, "Updated abstract")
        self.assertEqual(project.student_names, "Carol Dana")
        self.assertEqual(stats.projects_created, 0)
        self.assertEqual(stats.projects_updated, 1)
        self.assertEqual(stats.projects_deleted, 0)
        self.config.refresh_from_db()
        self.assertEqual(self.config.sync_count, 1)
        self.assertTrue(PastProjectSyncLog.objects.filter(projects_updated=1, projects_deleted=0).exists())

    def test_sync_adds_new_rows_without_changing_existing_uuid(self):
        sync_past_projects(self.config, records=[_record()])
        original = Project.objects.get()
        original_pk = original.pk

        stats = sync_past_projects(self.config, records=[_record(), _record(team="202", title="Second Project")])

        original.refresh_from_db()
        self.assertEqual(original.pk, original_pk)
        self.assertEqual(Project.objects.count(), 2)
        self.assertTrue(Project.objects.filter(team_number="202", project_title="Second Project").exists())
        self.assertEqual(stats.projects_created, 1)
        self.assertEqual(stats.projects_updated, 0)
        self.assertEqual(stats.projects_deleted, 0)

    def test_sync_removes_project_missing_from_latest_sheet_and_preserves_remaining_uuid(self):
        sync_past_projects(self.config, records=[_record(), _record(team="202", title="Second Project")])
        removed_pk = Project.objects.get(team_number="101").pk
        retained = Project.objects.get(team_number="202")
        retained_pk = retained.pk

        stats = sync_past_projects(self.config, records=[_record(team="202", title="Second Project")])

        retained.refresh_from_db()
        self.assertFalse(Project.objects.filter(pk=removed_pk).exists())
        self.assertEqual(retained.pk, retained_pk)
        self.assertEqual(Project.objects.filter(source=Project.Source.SHEET).count(), 1)
        self.assertEqual(stats.projects_created, 0)
        self.assertEqual(stats.projects_updated, 0)
        self.assertEqual(stats.projects_deleted, 1)
        self.assertTrue(PastProjectSyncLog.objects.filter(projects_created=0, projects_deleted=1).exists())

    def test_manual_rows_in_any_semester_never_touched(self):
        present = Semester.objects.create(year=2024, season=2, is_published=True)
        absent = Semester.objects.create(year=2019, season=1, is_published=True)
        manual_present = Project.objects.create(
            semester=present, project_title="Manual present", source=Project.Source.MANUAL
        )
        manual_absent = Project.objects.create(
            semester=absent, project_title="Manual absent", source=Project.Source.MANUAL
        )

        stats = sync_past_projects(self.config, records=[_record(title="Sheet present")])

        self.assertTrue(Project.objects.filter(pk=manual_present.pk).exists())
        self.assertTrue(Project.objects.filter(pk=manual_absent.pk).exists())
        manual_present.refresh_from_db()
        manual_absent.refresh_from_db()
        self.assertEqual(manual_present.project_title, "Manual present")
        self.assertEqual(manual_absent.project_title, "Manual absent")
        self.assertEqual(stats.projects_created, 1)
        self.assertEqual(stats.projects_updated, 0)
        self.assertEqual(stats.projects_deleted, 0)

    def test_unparseable_year_semester_skipped(self):
        records = [_record(year_semester="not-a-date"), _record(team="202")]
        stats = sync_past_projects(self.config, records=records)

        self.assertEqual(stats.rows_read, 2)
        self.assertEqual(stats.projects_created, 1)
        self.assertEqual(stats.rows_skipped, 1)

    def test_invalid_season_skipped(self):
        records = [_record(year_semester="2024-3 Summer"), _record(team="202")]
        stats = sync_past_projects(self.config, records=records)

        self.assertEqual(stats.projects_created, 1)
        self.assertEqual(stats.rows_skipped, 1)
        self.assertFalse(
            Semester.objects.filter(season=3).exists() and Project.objects.filter(semester__season=3).exists()
        )

    def test_blank_title_skipped(self):
        records = [_record(title=""), _record(team="202")]
        stats = sync_past_projects(self.config, records=records)

        self.assertEqual(stats.projects_created, 1)
        self.assertEqual(stats.rows_skipped, 1)

    def test_intra_sheet_duplicates_deduped(self):
        records = [_record(), _record()]  # same semester/class/team twice
        stats = sync_past_projects(self.config, records=records)

        self.assertEqual(stats.rows_read, 2)
        self.assertEqual(stats.projects_created, 1)
        self.assertEqual(stats.rows_skipped, 1)
        self.assertEqual(Project.objects.count(), 1)

    def test_empty_payload_raises_and_does_not_wipe(self):
        semester = Semester.objects.create(year=2024, season=2, is_published=True)
        existing = Project.objects.create(semester=semester, project_title="Keep me", source=Project.Source.SHEET)

        with self.assertRaises(SheetSyncError):
            sync_past_projects(self.config, records=[])

        # No deletion happened — the guard fires before the delete.
        self.assertTrue(Project.objects.filter(pk=existing.pk).exists())
        self.config.refresh_from_db()
        self.assertNotEqual(self.config.sync_error, "")
        log = PastProjectSyncLog.objects.get()
        self.assertEqual(log.status, PastProjectSyncLog.Status.FAILED)

    def test_all_rows_unparseable_raises(self):
        semester = Semester.objects.create(year=2024, season=2, is_published=True)
        existing = Project.objects.create(semester=semester, project_title="Keep me", source=Project.Source.SHEET)

        with self.assertRaises(SheetSyncError) as ctx:
            sync_past_projects(self.config, records=[_record(year_semester="bad")])
        self.assertIn("no importable past-project rows", str(ctx.exception))
        self.assertTrue(Project.objects.filter(pk=existing.pk).exists())
        log = PastProjectSyncLog.objects.get()
        self.assertEqual(log.status, PastProjectSyncLog.Status.FAILED)

    def test_generic_exception_wrapped_in_sheet_sync_error(self):
        with patch(
            "apps.projects.services.sheet_sync.runner.Project.objects.bulk_create",
            side_effect=RuntimeError("db gone"),
        ):
            with self.assertRaises(SheetSyncError) as ctx:
                sync_past_projects(self.config, records=[_record()])
        self.assertIn("db gone", str(ctx.exception))
        log = PastProjectSyncLog.objects.get()
        self.assertEqual(log.status, PastProjectSyncLog.Status.FAILED)

    def test_failure_skips_log_for_unsaved_config(self):
        unsaved = PastProjectsSheetConfig()
        with self.assertRaises(SheetSyncError):
            sync_past_projects(unsaved, records=[])
        self.assertFalse(PastProjectSyncLog.objects.exists())

    def test_success_updates_config_fields(self):
        sync_past_projects(self.config, records=[_record()])

        self.config.refresh_from_db()
        self.assertIsNotNone(self.config.last_synced_at)
        self.assertEqual(self.config.sync_error, "")
        self.assertEqual(self.config.sync_count, 1)

    def test_cache_invalidated_after_sync(self):
        cache.set("projects:past-all", "STALE")
        sync_past_projects(self.config, records=[_record()])
        self.assertIsNone(cache.get("projects:past-all"))

    def test_records_none_calls_fetch(self):
        with patch(
            "apps.projects.services.sheet_sync.runner.fetch_past_project_records",
            return_value=[_record()],
        ) as mock_fetch:
            sync_past_projects(self.config)
        mock_fetch.assert_called_once_with()
        self.assertEqual(Project.objects.count(), 1)

    def test_header_whitespace_is_normalized(self):
        # The live sheet ships headers with trailing spaces (e.g. "Project Title ").
        # get_all_records() keys rows by the exact header text, so the runner must
        # strip header whitespace before mapping or every row is dropped as titleless.
        record = {
            "Year-Semester ": "2024-2 Fall",
            " Class": "CSE",
            "Team#": "101",
            "Team Name": "Alpha",
            "Project Title ": "Smart App",
            "Organization": "TechCorp",
            "Industry": "Software",
            "Abstract": "An abstract",
            "Student Names": "Alice Bob",
        }
        stats = sync_past_projects(self.config, records=[record])

        self.assertEqual(stats.projects_created, 1)
        self.assertEqual(stats.rows_skipped, 0)
        project = Project.objects.get()
        self.assertEqual(project.project_title, "Smart App")
        self.assertEqual(project.class_code, "CSE")
