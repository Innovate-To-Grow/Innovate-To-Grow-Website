"""
Sync event registrations to a Google Sheet.

Target format (columns):
  Order | First Name | Last Name | Phone | When Started | Last Updated |
  Membership Primary | Membership Secondary | Ticket Type | <dynamic question columns>

Three sync modes:
  - schedule_registration_sync(event): debounced — waits 5s for more registrations, then batch-appends all new rows.
  - sync_registrations_to_sheet(event): full replace (admin recovery action).
  - _flush_pending_sync(event_id): internal — executes the batched append.
"""

import logging
import threading

from django.db import close_old_connections
from django.utils import timezone

from core.models import GoogleCredentialConfig
from event.models import Event, EventRegistration, RegistrationSheetSyncLog

logger = logging.getLogger(__name__)

# Debounce state: per-event timers.
_sync_timers: dict[str, threading.Timer] = {}
_sync_lock = threading.Lock()
DEBOUNCE_SECONDS = 15


class RegistrationSyncError(RuntimeError):
    """Raised when registration sheet sync fails."""


def _get_worksheet_by_gid(spreadsheet, worksheet_gid: int):
    return next((ws for ws in spreadsheet.worksheets() if ws.id == worksheet_gid), None)


def _get_worksheet(event: Event):
    """Open the configured worksheet for the event."""
    credentials = GoogleCredentialConfig.load()
    if not credentials.is_configured:
        raise RegistrationSyncError("No active Google service account is configured.")

    import gspread

    client = gspread.service_account_from_dict(credentials.get_credentials_info())
    spreadsheet = client.open_by_key(event.registration_sheet_id)

    if event.registration_sheet_gid is not None:
        worksheet = _get_worksheet_by_gid(spreadsheet, int(event.registration_sheet_gid))
        if worksheet is None:
            raise RegistrationSyncError("Registration worksheet GID not found in the spreadsheet.")
    else:
        worksheet = spreadsheet.sheet1

    return worksheet


def _build_header(event: Event, question_texts: list[str]) -> list[str]:
    header = [
        "Order",
        "First Name",
        "Last Name",
    ]
    if event.collect_phone:
        header.append("Phone")
    header += [
        "When Started",
        "Last Updated",
        "Membership Primary",
    ]
    if event.allow_secondary_email:
        header.append("Membership Secondary")
    header.append("Ticket Type")
    header.extend(question_texts)
    return header


def _build_row(registration: EventRegistration, event: Event, question_texts: list[str], order: int) -> list[str]:
    answers_map = {a["question_text"]: a["answer"] for a in registration.question_answers}

    row = [
        str(order),
        registration.attendee_first_name,
        registration.attendee_last_name,
    ]
    if event.collect_phone:
        row.append(registration.attendee_phone)
    row += [
        registration.created_at.strftime("%Y-%m-%d %H:%M"),
        registration.updated_at.strftime("%Y-%m-%d %H:%M"),
        registration.attendee_email,
    ]
    if event.allow_secondary_email:
        row.append(registration.attendee_secondary_email)
    row.append(registration.ticket.name)
    for qt in question_texts:
        row.append(answers_map.get(qt, ""))
    return row


# ---------------------------------------------------------------------------
# Debounced batch append (called per registration, batches into 1 API call)
# ---------------------------------------------------------------------------


def schedule_registration_sync(event: Event) -> None:
    """
    Schedule a batched sheet sync for this event after DEBOUNCE_SECONDS.

    If called again within the debounce window, the timer resets so multiple
    registrations arriving close together are merged into a single API call.
    Non-blocking — returns immediately.
    """
    if not event.registration_sheet_id:
        return

    event_id = str(event.pk)
    with _sync_lock:
        existing = _sync_timers.pop(event_id, None)
        if existing:
            existing.cancel()
        timer = threading.Timer(DEBOUNCE_SECONDS, _flush_pending_sync, args=[event_id])
        timer.daemon = True
        _sync_timers[event_id] = timer
        timer.start()


def _flush_pending_sync(event_id: str) -> None:
    """Execute the batched append — runs in a background thread after debounce."""
    with _sync_lock:
        _sync_timers.pop(event_id, None)

    try:
        # Background thread needs its own DB connection management.
        close_old_connections()

        event = Event.objects.get(pk=event_id)
        if not event.registration_sheet_id:
            return

        credentials = GoogleCredentialConfig.load()
        if not credentials.is_configured:
            _record_sync_failure(
                event,
                "No active Google service account is configured.",
                sync_type=RegistrationSheetSyncLog.SyncType.APPEND,
            )
            return

        # Find registrations created after the last sync.
        qs = EventRegistration.objects.filter(event=event).select_related("ticket").order_by("created_at")
        if event.registration_sheet_synced_at:
            new_registrations = list(qs.filter(created_at__gt=event.registration_sheet_synced_at))
        else:
            new_registrations = list(qs)

        if not new_registrations:
            event.registration_sheet_synced_at = timezone.now()
            event.registration_sheet_sync_error = ""
            event.save(
                update_fields=[
                    "registration_sheet_synced_at",
                    "registration_sheet_sync_error",
                    "updated_at",
                ]
            )
            RegistrationSheetSyncLog.objects.create(
                event=event,
                sync_type=RegistrationSheetSyncLog.SyncType.APPEND,
                status=RegistrationSheetSyncLog.Status.SUCCESS,
                rows_written=0,
            )
            return

        question_texts = list(event.questions.order_by("order").values_list("text", flat=True))
        start_order = event.registration_sheet_sync_count + 1

        rows = [_build_row(reg, event, question_texts, start_order + idx) for idx, reg in enumerate(new_registrations)]

        worksheet = _get_worksheet(event)

        # If sheet is empty (first sync), write header first.
        if start_order == 1:
            header = _build_header(event, question_texts)
            worksheet.append_rows([header] + rows, value_input_option="USER_ENTERED")
        else:
            worksheet.append_rows(rows, value_input_option="USER_ENTERED")

        new_count = event.registration_sheet_sync_count + len(rows)
        event.registration_sheet_synced_at = timezone.now()
        event.registration_sheet_sync_count = new_count
        event.registration_sheet_sync_error = ""
        event.save(
            update_fields=[
                "registration_sheet_synced_at",
                "registration_sheet_sync_count",
                "registration_sheet_sync_error",
                "updated_at",
            ]
        )
        RegistrationSheetSyncLog.objects.create(
            event=event,
            sync_type=RegistrationSheetSyncLog.SyncType.APPEND,
            status=RegistrationSheetSyncLog.Status.SUCCESS,
            rows_written=len(rows),
        )
        logger.info("Batch appended %d registrations to sheet for event %s.", len(rows), event.slug)

    except Exception as exc:
        logger.exception("Batch sheet sync failed for event %s.", event_id)
        try:
            event = Event.objects.get(pk=event_id)
            event.registration_sheet_synced_at = timezone.now()
            event.registration_sheet_sync_error = str(exc)
            event.save(update_fields=["registration_sheet_synced_at", "registration_sheet_sync_error", "updated_at"])
            RegistrationSheetSyncLog.objects.create(
                event=event,
                sync_type=RegistrationSheetSyncLog.SyncType.APPEND,
                status=RegistrationSheetSyncLog.Status.FAILED,
                rows_written=0,
                error_message=str(exc),
            )
        except Exception:
            logger.exception("Failed to record sync failure for event %s.", event_id)
    finally:
        close_old_connections()


# ---------------------------------------------------------------------------
# Full sync: replace entire sheet (admin recovery action)
# ---------------------------------------------------------------------------


def sync_registrations_to_sheet(event: Event) -> int:
    """
    Full replace of the Google Sheet with all registrations for the event.
    Use this for recovery, initial setup, or when the sheet gets out of sync.
    """
    if not event.registration_sheet_id:
        error_message = "Registration Google Sheet ID is not configured."
        _record_sync_failure(event, error_message, sync_type=RegistrationSheetSyncLog.SyncType.FULL)
        raise RegistrationSyncError(error_message)

    credentials = GoogleCredentialConfig.load()
    if not credentials.is_configured:
        error_message = "No active Google service account is configured."
        _record_sync_failure(event, error_message, sync_type=RegistrationSheetSyncLog.SyncType.FULL)
        raise RegistrationSyncError(error_message)

    registrations = list(EventRegistration.objects.filter(event=event).select_related("ticket").order_by("created_at"))

    question_texts = list(event.questions.order_by("order").values_list("text", flat=True))

    header = _build_header(event, question_texts)
    rows = [_build_row(reg, event, question_texts, idx + 1) for idx, reg in enumerate(registrations)]

    try:
        worksheet = _get_worksheet(event)
        worksheet.clear()
        worksheet.update([header] + rows, value_input_option="USER_ENTERED")
        logger.info("Full sync: %d registrations to sheet for event %s.", len(rows), event.slug)
    except RegistrationSyncError as exc:
        _record_sync_failure(event, str(exc), sync_type=RegistrationSheetSyncLog.SyncType.FULL)
        raise
    except Exception as exc:
        _record_sync_failure(event, str(exc), sync_type=RegistrationSheetSyncLog.SyncType.FULL)
        raise RegistrationSyncError(f"Failed to write to Google Sheet: {exc}") from exc

    event.registration_sheet_synced_at = timezone.now()
    event.registration_sheet_sync_count = len(rows)
    event.registration_sheet_sync_error = ""
    event.save(
        update_fields=[
            "registration_sheet_synced_at",
            "registration_sheet_sync_count",
            "registration_sheet_sync_error",
            "updated_at",
        ]
    )
    RegistrationSheetSyncLog.objects.create(
        event=event,
        sync_type=RegistrationSheetSyncLog.SyncType.FULL,
        status=RegistrationSheetSyncLog.Status.SUCCESS,
        rows_written=len(rows),
    )
    return len(rows)


def _record_sync_failure(event: Event, error_message: str, *, sync_type: str = "") -> None:
    event.registration_sheet_synced_at = timezone.now()
    event.registration_sheet_sync_error = error_message
    event.save(
        update_fields=[
            "registration_sheet_synced_at",
            "registration_sheet_sync_error",
            "updated_at",
        ]
    )
    if sync_type:
        RegistrationSheetSyncLog.objects.create(
            event=event,
            sync_type=sync_type,
            status=RegistrationSheetSyncLog.Status.FAILED,
            error_message=error_message,
        )
