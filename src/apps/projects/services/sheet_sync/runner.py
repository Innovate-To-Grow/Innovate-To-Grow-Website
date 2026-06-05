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


def sync_past_projects(
    config: PastProjectsSheetConfig,
    *,
    records: list[dict[str, Any]] | None = None,
    sync_type: str = "",
) -> PastProjectSyncStats:
    """Full-replace the Google-Sheet-sourced past projects from the configured sheet.

    Sheet-sourced rows (``Project.source == SHEET``) are deleted and recreated;
    manual/CSV rows are never touched. ``records`` injects the row list to bypass
    the network (used by tests). Failures are logged and re-raised as SheetSyncError.
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

    # Parse + replace inside one transaction so the semester auto-publish done by
    # resolve_project_row rolls back if bulk_create fails.
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

            dup_key = (resolved["semester"].pk, resolved["class_code"], resolved["team_number"])
            if dup_key in seen:
                stats.rows_skipped += 1
                continue
            seen.add(dup_key)

            touched_semester_pks.add(resolved["semester"].pk)
            parsed.append(resolved)

        if not parsed:
            raise SheetSyncError("The configured sheet contained no importable past-project rows.")

        # Full replace of sheet-sourced rows only — manual/CSV rows survive.
        Project.objects.filter(source=Project.Source.SHEET).delete()
        Project.objects.bulk_create([Project(source=Project.Source.SHEET, **fields) for fields in parsed])

        stats.projects_created = len(parsed)
        stats.semesters_touched = len(touched_semester_pks)

    # Mark synced without triggering ActiveModel save() side effects.
    PastProjectsSheetConfig.objects.filter(pk=config.pk).update(
        last_synced_at=timezone.now(),
        sync_error="",
        sync_count=stats.projects_created,
    )

    # bulk_create does not fire post_save, so clear the cache explicitly (post-commit).
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
