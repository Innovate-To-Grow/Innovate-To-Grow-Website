import logging
import threading

from django.db import close_old_connections
from django.db.models import F
from django.utils import timezone

from event.models import Event, EventRegistration, RegistrationSheetSyncLog

from .logs import record_sync_failure
from .rows import build_header, build_row

logger = logging.getLogger(__name__)

_sync_timers: dict[str, threading.Timer] = {}
_sync_lock = threading.Lock()


def schedule_registration_sync(event: Event) -> None:
    if not event.registration_sheet_id:
        return

    import event.services.registration_sheet_sync as sync_api

    event_id = str(event.pk)
    with _sync_lock:
        existing = _sync_timers.pop(event_id, None)
        if existing:
            existing.cancel()
        timer = threading.Timer(
            sync_api.DEBOUNCE_SECONDS,
            _flush_pending_sync,
            args=[event_id],
        )
        timer.daemon = True
        _sync_timers[event_id] = timer
        timer.start()


def _flush_pending_sync(event_id: str) -> None:
    with _sync_lock:
        _sync_timers.pop(event_id, None)

    try:
        close_old_connections()
        event = Event.objects.get(pk=event_id)
        if not event.registration_sheet_id:
            return

        import event.services.registration_sheet_sync as sync_api

        credentials = sync_api.GoogleCredentialConfig.load()
        if not credentials.is_configured:
            record_sync_failure(
                event,
                "No active Google service account is configured.",
                sync_type=RegistrationSheetSyncLog.SyncType.APPEND,
            )
            return

        registrations = _pending_registrations(event)
        if not registrations:
            _record_empty_append(event)
            return

        question_texts = list(event.questions.order_by("order").values_list("text", flat=True))
        event.refresh_from_db(fields=["registration_sheet_sync_count"])
        start_order = event.registration_sheet_sync_count + 1
        rows = [
            build_row(registration, event, question_texts, start_order + index)
            for index, registration in enumerate(registrations)
        ]

        worksheet = sync_api._get_worksheet(event)
        if start_order == 1:
            worksheet.append_rows([build_header(event, question_texts)] + rows, value_input_option="USER_ENTERED")
        else:
            worksheet.append_rows(rows, value_input_option="USER_ENTERED")

        _record_append_success(event, len(rows))
        logger.info(
            "Batch appended %d registrations to sheet for event %s.",
            len(rows),
            event.slug,
        )
    except Exception as exc:
        _record_append_exception(event_id, exc)
    finally:
        close_old_connections()


def _pending_registrations(event: Event) -> list[EventRegistration]:
    queryset = EventRegistration.objects.filter(event=event).select_related("ticket").order_by("created_at")
    if event.registration_sheet_synced_at:
        return list(queryset.filter(created_at__gt=event.registration_sheet_synced_at))
    return list(queryset)


def _record_empty_append(event: Event) -> None:
    now = timezone.now()
    Event.objects.filter(pk=event.pk).update(
        registration_sheet_synced_at=now,
        registration_sheet_sync_error="",
        updated_at=now,
    )
    RegistrationSheetSyncLog.objects.create(
        event=event,
        sync_type=RegistrationSheetSyncLog.SyncType.APPEND,
        status=RegistrationSheetSyncLog.Status.SUCCESS,
        rows_written=0,
    )


def _record_append_success(event: Event, row_count: int) -> None:
    Event.objects.filter(pk=event.pk).update(
        registration_sheet_sync_count=F("registration_sheet_sync_count") + row_count,
        registration_sheet_synced_at=timezone.now(),
        registration_sheet_sync_error="",
        updated_at=timezone.now(),
    )
    event.refresh_from_db(fields=["registration_sheet_sync_count", "registration_sheet_synced_at"])
    RegistrationSheetSyncLog.objects.create(
        event=event,
        sync_type=RegistrationSheetSyncLog.SyncType.APPEND,
        status=RegistrationSheetSyncLog.Status.SUCCESS,
        rows_written=row_count,
    )


def _record_append_exception(event_id: str, exc: Exception) -> None:
    logger.exception("Batch sheet sync failed for event %s.", event_id)
    try:
        event = Event.objects.get(pk=event_id)
        record_sync_failure(
            event,
            str(exc),
            sync_type=RegistrationSheetSyncLog.SyncType.APPEND,
            update_synced_at=True,
            rows_written=0,
        )
    except Exception:
        logger.exception("Failed to record sync failure for event %s.", event_id)
