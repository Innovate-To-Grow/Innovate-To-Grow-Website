from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.projects.models import PastProjectsSheetConfig, PastProjectSyncLog, Project
from apps.projects.services.hooks import resolve_project_row
from apps.projects.signals import _clear_project_caches

from .shared import PastProjectSyncStats, SheetSyncError
from .sheets import fetch_past_project_records

# Map the legacy Google-Sheet header text to Project field names. `get_all_records()`
# keys each row by the header row text, so we map by header (not by index like the
# CSV importer). "Year-Semester" is consumed separately by resolve_project_row.
COLUMN_MAP = {
    "Class": "class_code",
    "Team#": "team_number",
    "Team Name": "team_name",
    "Project Title": "project_title",
    "Organization": "organization",
    "Industry": "industry",
    "Abstract": "abstract",
    "Student Names": "student_names",
}

# Valid Semester.season values (1=Spring, 2=Fall). Other digits parsed out of the
# "Year-Semester" cell (e.g. a stray "2025-3 Summer") are rejected as unimportable.
_VALID_SEASONS = {1, 2}
_STABLE_KEY_FIELDS = ("semester", "class_code", "team_number")
_MUTABLE_PROJECT_FIELDS = tuple(field for field in COLUMN_MAP.values() if field not in _STABLE_KEY_FIELDS)


def _project_sync_key(fields_or_project) -> tuple:
    """Identity for a sheet-synced project: Year-Semester + Class + Team#."""
    if isinstance(fields_or_project, dict):
        return (
            fields_or_project["semester"].pk,
            fields_or_project["class_code"],
            fields_or_project["team_number"],
        )
    semester_id = fields_or_project.semester_id
    class_code = fields_or_project.class_code
    team_number = fields_or_project.team_number
    return (semester_id, class_code, team_number)


def sync_past_projects(
    config: PastProjectsSheetConfig,
    *,
    records: list[dict[str, Any]] | None = None,
    sync_type: str = "",
) -> PastProjectSyncStats:
    """Upsert the Google-Sheet-sourced past projects from the configured sheet.

    Existing sheet-sourced rows are matched by Year-Semester + Class + Team# so
    their UUIDs stay stable across syncs. Manual/CSV rows are never touched.
    ``records`` injects the row list to bypass the network (used by tests).
    Failures are logged and re-raised as SheetSyncError.
    """
    try:
        return _sync_past_projects(config, records=records, sync_type=sync_type)
    except Exception as exc:
        _record_sync_failure(config, exc, sync_type)
        if isinstance(exc, SheetSyncError):
            raise
        raise SheetSyncError(str(exc)) from exc


def _sync_past_projects(
    config: PastProjectsSheetConfig,
    *,
    records: list[dict[str, Any]] | None,
    sync_type: str,
) -> PastProjectSyncStats:
    if records is None:
        records = fetch_past_project_records()

    stats = PastProjectSyncStats(rows_read=len(records))

    # Parse + upsert inside one transaction so the semester auto-publish done by
    # resolve_project_row rolls back if the project write phase fails.
    with transaction.atomic():
        parsed: list[dict[str, Any]] = []
        touched_semester_pks: set[Any] = set()
        seen: set[tuple] = set()

        for raw in records:
            # Normalize header whitespace before mapping: the live sheet has headers
            # like "Project Title " (trailing space), and get_all_records() keys rows
            # by the exact header text, so a strict lookup would silently miss them.
            row = {str(key).strip(): value for key, value in raw.items()}
            mapped = {field: str(row.get(header, "")).strip() for header, field in COLUMN_MAP.items()}
            mapped["Year-Semester"] = str(row.get("Year-Semester", "")).strip()

            resolved = resolve_project_row(mapped, sheet_link=None)
            if resolved is None:
                stats.rows_skipped += 1
                continue
            if resolved["semester"].season not in _VALID_SEASONS:
                stats.rows_skipped += 1
                continue
            if not resolved.get("project_title"):
                stats.rows_skipped += 1
                continue

            dup_key = _project_sync_key(resolved)
            if dup_key in seen:
                stats.rows_skipped += 1
                continue
            seen.add(dup_key)

            touched_semester_pks.add(resolved["semester"].pk)
            parsed.append(resolved)

        if not parsed:
            raise SheetSyncError("The configured sheet contained no importable past-project rows.")

        existing_by_key: dict[tuple, Project] = {}
        duplicate_existing_ids = []
        for project in Project.objects.filter(source=Project.Source.SHEET).select_related("semester").order_by("pk"):
            key = _project_sync_key(project)
            if key in existing_by_key:
                duplicate_existing_ids.append(project.pk)
                continue
            existing_by_key[key] = project

        to_create = []
        to_update = []
        now = timezone.now()
        for fields in parsed:
            key = _project_sync_key(fields)
            existing = existing_by_key.get(key)
            if existing is None:
                to_create.append(Project(source=Project.Source.SHEET, **fields))
                continue

            changed = False
            for field in _MUTABLE_PROJECT_FIELDS:
                new_value = fields.get(field, "")
                if getattr(existing, field) != new_value:
                    setattr(existing, field, new_value)
                    changed = True
            if changed:
                existing.updated_at = now
                to_update.append(existing)

        stale_ids = duplicate_existing_ids + [project.pk for key, project in existing_by_key.items() if key not in seen]
        if stale_ids:
            deleted_count, _ = Project.objects.filter(pk__in=stale_ids, source=Project.Source.SHEET).delete()
            stats.projects_deleted = deleted_count
        if to_create:
            Project.objects.bulk_create(to_create)
        if to_update:
            Project.objects.bulk_update(to_update, [*_MUTABLE_PROJECT_FIELDS, "updated_at"])

        stats.projects_created = len(to_create)
        stats.projects_updated = len(to_update)
        stats.semesters_touched = len(touched_semester_pks)

    # Mark synced without triggering ActiveModel save() side effects.
    PastProjectsSheetConfig.objects.filter(pk=config.pk).update(
        last_synced_at=timezone.now(),
        sync_error="",
        sync_count=len(parsed),
    )

    # Bulk writes do not fire post_save, so clear the cache explicitly (post-commit).
    _clear_project_caches()

    _record_sync_success(config, stats, sync_type)
    return stats


def _record_sync_success(
    config: PastProjectsSheetConfig,
    stats: PastProjectSyncStats,
    sync_type: str,
) -> None:
    PastProjectSyncLog.objects.create(
        config=config,
        sync_type=sync_type or PastProjectSyncLog.SyncType.MANUAL,
        status=PastProjectSyncLog.Status.SUCCESS,
        rows_read=stats.rows_read,
        projects_created=stats.projects_created,
        projects_updated=stats.projects_updated,
        projects_deleted=stats.projects_deleted,
        semesters_touched=stats.semesters_touched,
        rows_skipped=stats.rows_skipped,
    )


def _record_sync_failure(config: PastProjectsSheetConfig, exc: Exception, sync_type: str) -> None:
    error_message = str(exc)
    if not config.pk or config._state.adding:
        return
    PastProjectsSheetConfig.objects.filter(pk=config.pk).update(sync_error=error_message[:4000])
    PastProjectSyncLog.objects.create(
        config=config,
        sync_type=sync_type or PastProjectSyncLog.SyncType.MANUAL,
        status=PastProjectSyncLog.Status.FAILED,
        error_message=error_message[:4000],
    )
