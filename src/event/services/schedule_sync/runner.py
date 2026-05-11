from __future__ import annotations

from typing import Any

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from event.models import (
    CurrentProjectSchedule,
    ScheduleSyncLog,
)

from .parsing import build_grand_winners, build_slot_rows, build_track_rows
from .projects import sync_projects_from_slots
from .shared import ScheduleSyncError, ScheduleSyncStats
from .sheets import fetch_schedule_sheet_records
from .writing import (
    clear_schedule,
    create_agenda_items,
    create_sections,
    create_slots,
    create_tracks,
)


def sync_schedule(
    config: CurrentProjectSchedule,
    *,
    tracks_records: list[dict[str, Any]] | None = None,
    projects_records: list[dict[str, Any]] | None = None,
    sync_type: str = "",
) -> ScheduleSyncStats:
    try:
        return _sync_schedule(
            config,
            tracks_records=tracks_records,
            projects_records=projects_records,
            sync_type=sync_type,
        )
    except Exception as exc:
        _record_sync_failure(config, exc, sync_type)
        if isinstance(exc, ScheduleSyncError):
            raise
        raise ScheduleSyncError(str(exc)) from exc


def _sync_schedule(
    config: CurrentProjectSchedule,
    *,
    tracks_records: list[dict[str, Any]] | None,
    projects_records: list[dict[str, Any]] | None,
    sync_type: str,
) -> ScheduleSyncStats:
    if tracks_records is None or projects_records is None:
        tracks_records, projects_records = fetch_schedule_sheet_records()

    parsed_tracks = build_track_rows(tracks_records)
    grand_winners = build_grand_winners(tracks_records)
    parsed_slots = build_slot_rows(projects_records)
    if not parsed_tracks or not parsed_slots:
        raise ScheduleSyncError("The configured sheet does not contain any schedule tracks or slots.")

    current_projects, touched_project_pks = sync_projects_from_slots(config, parsed_slots)
    stats = ScheduleSyncStats()

    with transaction.atomic():
        clear_schedule(config, touched_project_pks)
        sections_by_code = create_sections(config, parsed_tracks, parsed_slots, stats)
        tracks_by_number = create_tracks(sections_by_code, parsed_tracks, stats)
        create_slots(tracks_by_number, current_projects, parsed_slots, stats)
        create_agenda_items(config, stats)

    CurrentProjectSchedule.objects.filter(pk=config.pk).update(
        last_synced_at=timezone.now(),
        sync_error="",
        grand_winners=grand_winners,
    )
    cache.delete("event:current-projects")
    _record_sync_success(config, stats, sync_type)
    return stats


def _record_sync_success(
    config: CurrentProjectSchedule,
    stats: ScheduleSyncStats,
    sync_type: str,
) -> None:
    ScheduleSyncLog.objects.create(
        config=config,
        sync_type=sync_type or ScheduleSyncLog.SyncType.MANUAL,
        status=ScheduleSyncLog.Status.SUCCESS,
        sections_created=stats.sections_created,
        tracks_created=stats.tracks_created,
        slots_created=stats.slots_created,
    )


def _record_sync_failure(config: CurrentProjectSchedule, exc: Exception, sync_type: str) -> None:
    error_message = str(exc)
    if not config.pk or config._state.adding:
        return
    CurrentProjectSchedule.objects.filter(pk=config.pk).update(sync_error=error_message[:4000])
    ScheduleSyncLog.objects.create(
        config=config,
        sync_type=sync_type or ScheduleSyncLog.SyncType.MANUAL,
        status=ScheduleSyncLog.Status.FAILED,
        error_message=error_message[:4000],
    )
