"""One pull of the past-projects sheet: compare it with the projects it made before, then create, update and
unpublish them, and record the outcome on the sheet config."""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.projects.models import PastProjectsSheetConfig, PastProjectSyncLog, Project
from apps.projects.signals import _clear_project_caches

from .rows import _MUTABLE_PROJECT_FIELDS, _parse_records, _project_sync_key
from .shared import PastProjectSyncStats, SheetSyncError
from .sheets import fetch_past_project_records


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


def _existing_sheet_projects():
    """Sheet-sourced projects by sync key, plus the ids of any duplicates of a key (oldest wins)."""
    existing_by_key: dict[tuple, Project] = {}
    duplicate_existing_ids = []
    for project in Project.objects.filter(source=Project.Source.SHEET).select_related("semester").order_by("pk"):
        key = _project_sync_key(project)
        if key in existing_by_key:
            duplicate_existing_ids.append(project.pk)
            continue
        existing_by_key[key] = project
    return existing_by_key, duplicate_existing_ids


def _diff_projects(parsed, existing_by_key):
    """Projects to create, and existing ones whose mutable fields changed (already updated in memory)."""
    to_create = []
    to_update = []
    now = timezone.now()
    for fields in parsed:
        existing = existing_by_key.get(_project_sync_key(fields))
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
    return to_create, to_update


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
        parsed, seen, touched_semester_pks = _parse_records(records, stats)
        if not parsed:
            raise SheetSyncError("The configured sheet contained no importable past-project rows.")

        existing_by_key, duplicate_existing_ids = _existing_sheet_projects()
        to_create, to_update = _diff_projects(parsed, existing_by_key)

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
