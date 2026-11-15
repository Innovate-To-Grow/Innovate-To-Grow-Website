"""Reading the destination and planning a sync, without writing: shared by every sync, and the inspection view."""

from django.db.models import Prefetch, prefetch_related_objects

from apps.event.models import (
    EventRegistration,
    Question,
    RegistrationSheetSyncConfig,
    RegistrationSheetSyncRecord,
)

from ..plan.planner import plan_sync
from ..plan.schema import registration_fields, registration_values
from ..worksheet.sheets import RegistrationSyncConflict, RegistrationSyncError
from ..worksheet.snapshot import lock_destination, read_snapshot


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
