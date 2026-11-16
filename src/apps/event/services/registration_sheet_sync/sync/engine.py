"""Managed registration exports with non-mutating inspection and safe adoption."""

from django.db import transaction
from django.utils import timezone

from apps.event.models import (
    Event,
    RegistrationSheetSyncLog,
    RegistrationSheetSyncRecord,
)

from ..schedule.state import begin_sync, complete_sync
from ..worksheet.batch_updates import apply_plan
from ..worksheet.sheets import RegistrationSyncError, service_account_email
from ..worksheet.snapshot import backup_worksheet
from .prepare import _config_for, _prepare, _verify_plan
from .run_failures import _record_failed_run, _rows_written, _RunState


def _record_success(event, plan, snapshot, *, generation, sync_type, cursor_from, started_at):
    now = timezone.now()
    RegistrationSheetSyncRecord.objects.bulk_create(
        [RegistrationSheetSyncRecord(event=event, registration_id=identity) for identity in plan.active_ids],
        ignore_conflicts=True,
    )
    RegistrationSheetSyncRecord.objects.filter(event=event, registration_id__in=plan.active_ids).update(synced_at=now)
    if plan.stale_rows:
        # Receipts let later managed syncs recognize rows adopted as deleted.
        stale_ids = [stale["registration_id"] for stale in plan.stale_rows]
        RegistrationSheetSyncRecord.objects.bulk_create(
            [RegistrationSheetSyncRecord(event=event, registration_id=identity) for identity in stale_ids],
            ignore_conflicts=True,
        )
        stale_records = RegistrationSheetSyncRecord.objects.filter(event=event, registration_id__in=stale_ids)
        stale_records.update(synced_at=now)
        stale_records.filter(deleted_at__isnull=True).update(deleted_at=now)
    event_updates = {
        "registration_sheet_synced_at": now,
        "registration_sheet_sync_count": len(plan.active_ids),
        "registration_sheet_sync_error": "",
    }
    if event.registration_sheet_gid is None:
        # A one-time default selection must not drift when organizers reorder tabs.
        event_updates["registration_sheet_gid"] = snapshot.sheet_id
    Event.objects.filter(pk=event.pk).update(**event_updates)
    written = plan.counts["added"] + plan.counts["updated"] + plan.counts["deleted"]
    RegistrationSheetSyncLog.objects.create(
        event=event,
        sync_type=sync_type,
        status=RegistrationSheetSyncLog.Status.SUCCESS,
        rows_written=written,
        cursor_from=cursor_from,
        cursor_to=started_at,
        selected_registration_ids=plan.active_ids,
        details={
            "generation": generation,
            "sheet_id": event.registration_sheet_id,
            "worksheet_gid": snapshot.sheet_id,
            **plan.counts,
            "conflicts": 0,
        },
    )
    return written


def _write_plan(worksheet, snapshot, plan, *, event, config, credentials) -> None:
    apply_plan(
        worksheet,
        snapshot,
        plan,
        event_id=event.pk,
        header_row=config.header_row,
        editor_email=service_account_email(credentials),
    )


def _sync_locked(run: _RunState, *, adopt_legacy, expected_fingerprint, generation, sync_type, started_at) -> int:
    with transaction.atomic():
        event = run.event = Event.objects.select_for_update(no_key=True).get(pk=run.event.pk)
        # Destination and mappings may have changed while this run waited for the event lock.
        config = _config_for(event)
        cursor_from = event.registration_sheet_synced_at
        worksheet, run.snapshot, run.plan, credentials = _prepare(event, config, lock=True)
        _verify_plan(run.plan, adopt_legacy=adopt_legacy, expected_fingerprint=expected_fingerprint)
        if run.plan.requires_adoption:
            run.backup = backup_worksheet(worksheet)
        _write_plan(worksheet, run.snapshot, run.plan, event=event, config=config, credentials=credentials)
        run.provider_write_completed = True
        return _record_success(
            event,
            run.plan,
            run.snapshot,
            generation=generation,
            sync_type=sync_type,
            cursor_from=cursor_from,
            started_at=started_at,
        )


def sync_registrations_to_sheet(
    event, *, adopt_legacy=False, expected_fingerprint=None, job=None, sync_type=RegistrationSheetSyncLog.SyncType.FULL
):
    state = begin_sync(event.pk, job=job)
    generation = state["captured_generation"]
    started_at = timezone.now()
    run = _RunState(event=event)
    try:
        written = _sync_locked(
            run,
            adopt_legacy=adopt_legacy,
            expected_fingerprint=expected_fingerprint,
            generation=generation,
            sync_type=sync_type,
            started_at=started_at,
        )
        complete_sync(event.pk, generation, **run.plan.counts)
        return written
    except Exception as exc:
        plan, snapshot, backup = run.plan, run.snapshot, run.backup
        conflicts = len(plan.conflicts) if plan is not None else 0
        _record_failed_run(
            run.event,
            exc,
            generation=generation,
            sync_type=sync_type,
            started_at=started_at,
            rows_written=_rows_written(plan, run.provider_write_completed),
            conflicts=conflicts,
            selected_registration_ids=plan.active_ids if plan else [],
            details={
                "worksheet_gid": snapshot.sheet_id if snapshot else run.event.registration_sheet_gid,
                "backup_worksheet_gid": backup.id if backup else None,
                "provider_write_completed": run.provider_write_completed,
                **(plan.counts if plan else {}),
                "conflicts": conflicts,
            },
        )
        if isinstance(exc, RegistrationSyncError):
            raise
        raise RegistrationSyncError(f"Failed to write to Google Sheet: {exc}") from exc
