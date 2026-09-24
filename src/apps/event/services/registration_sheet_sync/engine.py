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

from .logs import record_sync_failure
from .planner import plan_sync
from .provider import apply_plan, backup_worksheet, lock_destination, read_snapshot, spreadsheet_for
from .scheduler import begin_sync, complete_sync, fail_sync
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


def sync_registrations_to_sheet(
    event, *, adopt_legacy=False, expected_fingerprint=None, job=None, sync_type=RegistrationSheetSyncLog.SyncType.FULL
):
    state = begin_sync(event.pk, job=job)
    generation = state["captured_generation"]
    started_at = timezone.now()
    plan = None
    snapshot = backup = None
    provider_write_completed = False
    try:
        with transaction.atomic():
            event = Event.objects.select_for_update(no_key=True).get(pk=event.pk)
            # Destination and mappings may have changed while this run waited for the event lock.
            config = _config_for(event)
            cursor_from = event.registration_sheet_synced_at
            worksheet, snapshot, plan, credentials = _prepare(event, config, lock=True)
            _verify_plan(plan, adopt_legacy=adopt_legacy, expected_fingerprint=expected_fingerprint)
            if plan.requires_adoption:
                backup = backup_worksheet(worksheet)
            apply_plan(
                worksheet,
                snapshot,
                plan,
                event_id=event.pk,
                header_row=config.header_row,
                editor_email=service_account_email(credentials),
            )
            provider_write_completed = True
            written = _record_success(
                event,
                plan,
                snapshot,
                generation=generation,
                sync_type=sync_type,
                cursor_from=cursor_from,
                started_at=started_at,
            )
        complete_sync(event.pk, generation, **plan.counts)
        return written
    except Exception as exc:
        blocked = isinstance(exc, RegistrationSyncConflict)
        conflicts = len(plan.conflicts) if plan is not None else 0
        fail_sync(event.pk, generation, str(exc), blocked=blocked, conflicts=conflicts)
        record_sync_failure(
            event,
            str(exc),
            sync_type=sync_type,
            rows_written=sum(plan.counts[key] for key in ("added", "updated", "deleted"))
            if provider_write_completed
            else 0,
            cursor_to=started_at,
            selected_registration_ids=plan.active_ids if plan else [],
            details={
                "generation": generation,
                "sheet_id": event.registration_sheet_id,
                "worksheet_gid": snapshot.sheet_id if snapshot else event.registration_sheet_gid,
                "backup_worksheet_gid": backup.id if backup else None,
                "provider_write_completed": provider_write_completed,
                **(plan.counts if plan else {}),
                "conflicts": conflicts,
            },
        )
        if isinstance(exc, RegistrationSyncError):
            raise
        raise RegistrationSyncError(f"Failed to write to Google Sheet: {exc}") from exc


def create_registration_worksheet(event, *, expected_fingerprint=None):
    """Back up and preserve the old worksheet; select a fresh populated export only on success."""
    state = begin_sync(event.pk)
    generation = state["captured_generation"]
    started_at = timezone.now()
    backup = new_worksheet = None
    plan = None
    provider_write_completed = False
    try:
        with transaction.atomic():
            event = Event.objects.select_for_update(no_key=True).get(pk=event.pk)
            config = _config_for(event)
            worksheet, snapshot, old_plan, credentials = _prepare(event, config, lock=True)
            if expected_fingerprint is None or old_plan.fingerprint != expected_fingerprint:
                raise RegistrationSyncConflict("Creating a new worksheet requires a current reviewed preview.")
            if read_snapshot(worksheet).fingerprint() != snapshot.fingerprint():
                raise RegistrationSyncConflict("The worksheet changed. Preview again before creating a new worksheet.")
            backup = backup_worksheet(worksheet)
            new_worksheet = spreadsheet_for(worksheet).add_worksheet(
                title=f"Registrations {datetime.now(UTC).strftime('%Y%m%d-%H%M%S-%f')}",
                rows=max(100, len(old_plan.active_ids) + config.header_row),
                cols=max(26, len(old_plan.columns)),
            )
            config.column_mappings = {}
            _, new_snapshot, plan, _ = _prepare(event, config, worksheet=new_worksheet, lock=True)
            _verify_plan(plan)
            apply_plan(
                new_worksheet,
                new_snapshot,
                plan,
                event_id=event.pk,
                header_row=config.header_row,
                editor_email=service_account_email(credentials),
            )
            provider_write_completed = True
            Event.objects.filter(pk=event.pk).update(registration_sheet_gid=new_worksheet.id)
            RegistrationSheetSyncConfig.objects.filter(pk=config.pk).update(column_mappings={})
            _record_success(
                event,
                plan,
                new_snapshot,
                generation=generation,
                sync_type=RegistrationSheetSyncLog.SyncType.FULL,
                cursor_from=event.registration_sheet_synced_at,
                started_at=started_at,
            )
        complete_sync(event.pk, generation, **plan.counts)
        return new_worksheet.id
    except Exception as exc:
        fail_sync(event.pk, generation, str(exc), blocked=isinstance(exc, RegistrationSyncConflict))
        record_sync_failure(
            event,
            str(exc),
            sync_type=RegistrationSheetSyncLog.SyncType.FULL,
            rows_written=sum(plan.counts[key] for key in ("added", "updated", "deleted"))
            if provider_write_completed
            else 0,
            cursor_to=started_at,
            details={
                "generation": generation,
                "sheet_id": event.registration_sheet_id,
                "worksheet_gid": event.registration_sheet_gid,
                "backup_worksheet_gid": backup.id if backup else None,
                "created_worksheet_gid": new_worksheet.id if new_worksheet else None,
                "provider_write_completed": provider_write_completed,
                **(plan.counts if plan else {}),
            },
        )
        if isinstance(exc, RegistrationSyncError):
            raise
        raise RegistrationSyncError(f"Failed to create registration worksheet: {exc}") from exc
