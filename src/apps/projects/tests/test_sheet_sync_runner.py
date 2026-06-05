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


def _record(year_semester="2024-2 Fall", team="101", title="Smart App", cls="CSE"):
    return {
        "Year-Semester": year_semester,
        "Class": cls,
        "Team#": team,
        "Team Name": "Alpha",
        "Project Title": title,
        "Organization": "TechCorp",
        "Industry": "Software",
        "Abstract": "An abstract",
        "Student Names": "Alice Bob",
    }


class SyncPastProjectsRunnerTest(TestCase):
    def setUp(self):
        self.config = PastProjectsSheetConfig.objects.create(name="Prod", is_active=True)

    def test_full_replace_creates_projects_and_publishes_semester(self):
        stats = sync_past_projects(self.config, records=[_record()])

        self.assertEqual(stats.rows_read, 1)
        self.assertEqual(stats.projects_created, 1)
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

    def test_full_replace_only_deletes_sheet_rows(self):
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

        sync_past_projects(self.config, records=[_record()])

        # The stale sheet row in the same semester is gone; the manual row survives.
        self.assertFalse(Project.objects.filter(pk=stale_sheet.pk).exists())
        self.assertTrue(Project.objects.filter(pk=manual.pk).exists())
        self.assertEqual(Project.objects.filter(source=Project.Source.SHEET).count(), 1)

    def test_manual_rows_in_any_semester_never_touched(self):
        present = Semester.objects.create(year=2024, season=2, is_published=True)
        absent = Semester.objects.create(year=2019, season=1, is_published=True)
        manual_present = Project.objects.create(
            semester=present, project_title="Manual present", source=Project.Source.MANUAL
        )
        manual_absent = Project.objects.create(
            semester=absent, project_title="Manual absent", source=Project.Source.MANUAL
        )

        sync_past_projects(self.config, records=[_record()])

        self.assertTrue(Project.objects.filter(pk=manual_present.pk).exists())
        self.assertTrue(Project.objects.filter(pk=manual_absent.pk).exists())

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
        with self.assertRaises(SheetSyncError) as ctx:
            sync_past_projects(self.config, records=[_record(year_semester="bad")])
        self.assertIn("no importable past-project rows", str(ctx.exception))
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
