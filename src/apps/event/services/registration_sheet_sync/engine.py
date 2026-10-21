"""Managed registration exports with non-mutating inspection and safe adoption."""

from datetime import UTC, datetime

from django.db import transaction
from django.db.models import Prefetch, prefetch_related_objects
from django.utils import timezone

from apps.event.models import (
    Event,
    EventRegistration,
    Question,
    RegistrationSheetSyncConfig,
    RegistrationSheetSyncLog,
    RegistrationSheetSyncRecord,
)

from .planner import plan_sync
from .provider import apply_plan, backup_worksheet, lock_destination, read_snapshot, spreadsheet_for
from .run_failures import _record_failed_run, _rows_written, _RunState
from .scheduler import begin_sync, complete_sync
from .schema import registration_fields, registration_values
from .sheets import RegistrationSyncConflict, RegistrationSyncError, service_account_email


def _config_for(event):
    return RegistrationSheetSyncConfig.objects.filter(event=event).first() or RegistrationSheetSyncConfig(event=event)


def _prepare(event, config, worksheet=None, *, lock=False):
    import apps.event.services.registration_sheet_sync as api

    if not event.registration_sheet_id:
        raise RegistrationSyncError("Registration Google Sheet ID is not configured.")
    config.full_clean()
    credentials = api.GoogleCredentialConfig.load()
    if not credentials.is_configured:
        raise RegistrationSyncError("No active Google service account is configured.")
    worksheet = worksheet or api._get_worksheet(event)
    if lock:
        lock_destination(getattr(worksheet, "spreadsheet_id", None) or event.registration_sheet_id, worksheet.id)
    snapshot = read_snapshot(worksheet)
    prefetch_related_objects([event], Prefetch("questions", queryset=Question.objects.order_by("order", "pk")))
    fields = registration_fields(event, config)
    registrations = list(
        EventRegistration.objects.filter(event=event).select_related("ticket").order_by("created_at", "pk")
    )
    values = {
        str(registration.pk): registration_values(registration, event, index + 1, fields)
        for index, registration in enumerate(registrations)
    }
    receipts = list(RegistrationSheetSyncRecord.objects.filter(event=event))
    known = {str(record.registration_id) for record in receipts if record.synced_at}
    deleted = {str(record.registration_id) for record in receipts if record.deleted_at}
    plan = plan_sync(
        snapshot,
        fields=fields,
        current_values=values,
        deleted_ids=deleted,
        known_ids=known,
        event_id=event.pk,
        config=config,
    )
    if plan.stale_rows:
        foreign = {
            str(identity)
            for identity in EventRegistration.objects.filter(
                pk__in=[stale["registration_id"] for stale in plan.stale_rows]
            ).values_list("pk", flat=True)
        }
        for stale in plan.stale_rows:
            if stale["registration_id"] in foreign:
                plan.conflicts.append(
                    f"Row {stale['row']} belongs to a registration from a different event. Choose a separate worksheet."
                )
    return worksheet, snapshot, plan, credentials


def inspect_registration_sheet(event, *, config=None):
    """Read provider/source state only; never create configuration, jobs or backups."""
    try:
        config = config or _config_for(event)
        _, snapshot, plan, _ = _prepare(event, config)
    except RegistrationSyncError:
        raise
    except Exception as exc:
        raise RegistrationSyncError(f"Unable to inspect registration worksheet: {exc}") from exc
    header = snapshot.values[config.header_row - 1] if len(snapshot.values) >= config.header_row else []
    return {
        "connection": {
            "sheet_id": event.registration_sheet_id,
            "worksheet_id": snapshot.sheet_id,
            "worksheet_title": snapshot.title,
            "header_row": config.header_row,
        },
        "columns": plan.columns,
        "existing_columns": [{"column": index + 1, "label": label} for index, label in enumerate(header)],
        "counts": plan.counts,
        "conflicts": plan.conflicts,
        "legacy_matches": plan.legacy_matches,
        "stale_rows": plan.stale_rows,
        "requires_adoption": plan.requires_adoption,
        "can_sync": not plan.conflicts and not plan.requires_adoption,
        "fingerprint": plan.fingerprint,
    }


def _verify_plan(plan, *, adopt_legacy=False, expected_fingerprint=None):
    if expected_fingerprint is not None and plan.fingerprint != expected_fingerprint:
        raise RegistrationSyncConflict(
            "The preview is no longer current. Preview the worksheet again before applying changes."
        )
    if plan.conflicts:
        raise RegistrationSyncConflict(" ".join(plan.conflicts))
    if plan.requires_adoption and not adopt_legacy:
        raise RegistrationSyncConflict(
            "Existing rows need reviewed legacy adoption before automatic sync can continue."
        )
    if plan.requires_adoption and not expected_fingerprint:
        raise RegistrationSyncConflict("Legacy adoption requires a current reviewed preview.")


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


def _add_fresh_worksheet(worksheet, old_plan, config):
    return spreadsheet_for(worksheet).add_worksheet(
        title=f"Registrations {datetime.now(UTC).strftime('%Y%m%d-%H%M%S-%f')}",
        rows=max(100, len(old_plan.active_ids) + config.header_row),
        cols=max(26, len(old_plan.columns)),
    )


def _create_locked(run: _RunState, *, expected_fingerprint, generation, started_at):
    with transaction.atomic():
        event = run.event = Event.objects.select_for_update(no_key=True).get(pk=run.event.pk)
        config = _config_for(event)
        worksheet, snapshot, old_plan, credentials = _prepare(event, config, lock=True)
        if expected_fingerprint is None or old_plan.fingerprint != expected_fingerprint:
            raise RegistrationSyncConflict("Creating a new worksheet requires a current reviewed preview.")
        if read_snapshot(worksheet).fingerprint() != snapshot.fingerprint():
            raise RegistrationSyncConflict("The worksheet changed. Preview again before creating a new worksheet.")
        run.backup = backup_worksheet(worksheet)
        new_worksheet = run.new_worksheet = _add_fresh_worksheet(worksheet, old_plan, config)
        config.column_mappings = {}
        _, new_snapshot, run.plan, _ = _prepare(event, config, worksheet=new_worksheet, lock=True)
        _verify_plan(run.plan)
        _write_plan(new_worksheet, new_snapshot, run.plan, event=event, config=config, credentials=credentials)
        run.provider_write_completed = True
        Event.objects.filter(pk=event.pk).update(registration_sheet_gid=new_worksheet.id)
        RegistrationSheetSyncConfig.objects.filter(pk=config.pk).update(column_mappings={})
        _record_success(
            event,
            run.plan,
            new_snapshot,
            generation=generation,
            sync_type=RegistrationSheetSyncLog.SyncType.FULL,
            cursor_from=event.registration_sheet_synced_at,
            started_at=started_at,
        )
    return new_worksheet.id


def create_registration_worksheet(event, *, expected_fingerprint=None):
    """Back up and preserve the old worksheet; select a fresh populated export only on success."""
    state = begin_sync(event.pk)
    generation = state["captured_generation"]
    started_at = timezone.now()
    run = _RunState(event=event)
    try:
        worksheet_id = _create_locked(
            run, expected_fingerprint=expected_fingerprint, generation=generation, started_at=started_at
        )
        complete_sync(event.pk, generation, **run.plan.counts)
        return worksheet_id
    except Exception as exc:
        _record_failed_run(
            run.event,
            exc,
            generation=generation,
            sync_type=RegistrationSheetSyncLog.SyncType.FULL,
            started_at=started_at,
            rows_written=_rows_written(run.plan, run.provider_write_completed),
            details={
                "worksheet_gid": run.event.registration_sheet_gid,
                "backup_worksheet_gid": run.backup.id if run.backup else None,
                "created_worksheet_gid": run.new_worksheet.id if run.new_worksheet else None,
                "provider_write_completed": run.provider_write_completed,
                **(run.plan.counts if run.plan else {}),
            },
        )
        if isinstance(exc, RegistrationSyncError):
            raise
        raise RegistrationSyncError(f"Failed to create registration worksheet: {exc}") from exc
