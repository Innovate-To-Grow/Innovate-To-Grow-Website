import logging
import threading

from django.db import close_old_connections, transaction
from django.utils import timezone

from apps.event.models import Event, EventRegistration, RegistrationSheetSyncLog

from .logs import record_sync_failure
from .rows import build_header, build_row
from .sheets import (
    ensure_registration_id_protected,
    read_sheet_values,
    registration_ids_from_values,
    service_account_email,
)

logger = logging.getLogger(__name__)
_sync_timers: dict[str, threading.Timer] = {}
_sync_lock = threading.Lock()


def schedule_registration_sync(event: Event, *, trigger_id=None) -> None:
    if not event.registration_sheet_id:
        return

    from apps.core.services.background_jobs import enqueue_job, jobs_enabled

    event_id = str(event.pk)

    if jobs_enabled():
        # Deliberately insert immediately. When the caller is creating a
        # registration inside transaction.atomic(), this outbox row commits or
        # rolls back with the registration.
        enqueue_job(
            kind="event.registration_sheet_sync",
            dedupe_key=f"{event_id}:{trigger_id or timezone.now().isoformat()}",
            payload={"event_id": event_id},
            can_retry_after_claim=True,
        )
        return

    # The pre-outbox fallback remains non-blocking and starts only after the
    # registration commits, so the timer's connection can see the new row.
    transaction.on_commit(lambda: _schedule_in_process_sync(event_id), robust=True)


def _schedule_in_process_sync(event_id: str) -> None:
    import apps.event.services.registration_sheet_sync as sync_api

    with _sync_lock:
        existing = _sync_timers.pop(event_id, None)
        if existing is not None:
            existing.cancel()
        timer = None
        try:
            timer = threading.Timer(
                sync_api.DEBOUNCE_SECONDS,
                _run_in_process_sync,
                args=[event_id],
            )
            timer.daemon = True
            _sync_timers[event_id] = timer
            timer.start()
        except Exception:  # noqa: BLE001 - a best-effort timer must not break the caller.
            if _sync_timers.get(event_id) is timer:
                _sync_timers.pop(event_id, None)
            logger.exception("Unable to start the registration sheet sync timer for event %s", event_id)


def _run_in_process_sync(event_id: str) -> None:
    with _sync_lock:
        if _sync_timers.get(event_id) is not threading.current_thread():
            # A newer debounce timer replaced this one while it was waking up.
            return
        _sync_timers.pop(event_id, None)
    _flush_pending_sync(event_id)


def _flush_pending_sync(event_id: str, *, raise_errors: bool = False) -> None:
    cursor_from = None
    cursor_to = None
    selected_ids: list[str] = []
    try:
        close_old_connections()
        with transaction.atomic():
            # Hold one event-row lock through selection, provider write, and
            # cursor advancement so two workers cannot append the same range.
            event = Event.objects.select_for_update(no_key=True).get(pk=event_id)
            if not event.registration_sheet_id:
                return

            import apps.event.services.registration_sheet_sync as sync_api

            credentials = sync_api.GoogleCredentialConfig.load()
            if not credentials.is_configured:
                raise RuntimeError("No active Google service account is configured.")

            cursor_from = event.registration_sheet_synced_at
            cursor_to = timezone.now()
            registrations = _pending_registrations(event, cutoff=cursor_to)
            selected_ids = [str(registration.pk) for registration in registrations]
            if not registrations:
                _record_empty_append(
                    event,
                    cursor_from=cursor_from,
                    cursor_to=cursor_to,
                )
                return

            question_texts = list(event.questions.order_by("order").values_list("text", flat=True))
            header = build_header(event, question_texts)
            worksheet = sync_api._get_worksheet(event)
            sheet_values = read_sheet_values(worksheet)
            existing_ids = registration_ids_from_values(
                sheet_values,
                expected_header=header,
            )
            missing = [registration for registration in registrations if str(registration.pk) not in existing_ids]
            existing_row_count = max(0, len(sheet_values) - 1)
            start_order = max(event.registration_sheet_sync_count, existing_row_count) + 1
            rows = [
                build_row(registration, event, question_texts, start_order + index)
                for index, registration in enumerate(missing)
            ]

            if not sheet_values:
                worksheet.append_rows(
                    [header] + rows,
                    value_input_option="USER_ENTERED",
                )
            elif rows:
                worksheet.append_rows(rows, value_input_option="USER_ENTERED")
            ensure_registration_id_protected(
                worksheet,
                header,
                editor_email=service_account_email(credentials),
            )

            total_at_cutoff = EventRegistration.objects.filter(
                event=event,
                created_at__lte=cursor_to,
            ).count()
            _record_append_success(
                event,
                row_count=len(rows),
                total_count=total_at_cutoff,
                cursor_from=cursor_from,
                cursor_to=cursor_to,
                selected_registration_ids=selected_ids,
            )
            logger.info(
                "Batch appended %d of %d selected registrations to sheet for event %s.",
                len(rows),
                len(registrations),
                event.slug,
            )
    except Event.DoesNotExist:
        logger.exception("Registration sync event %s no longer exists.", event_id)
        if raise_errors:
            raise
    except Exception as exc:
        _record_append_exception(
            event_id,
            exc,
            cursor_from=cursor_from,
            cursor_to=cursor_to,
            selected_registration_ids=selected_ids,
        )
        if raise_errors:
            raise
    finally:
        close_old_connections()


def _pending_registrations(event: Event, *, cutoff=None) -> list[EventRegistration]:
    """Return the complete snapshot through ``cutoff``.

    The cursor is audit metadata, not a selection boundary. An insert can obtain
    ``created_at`` before the cutoff yet remain invisible until after this
    transaction's SELECT. Selecting the full snapshot on every run and
    deduplicating by Registration ID in the sheet prevents that commit-order
    race from skipping the row permanently.
    """
    cutoff = cutoff or timezone.now()
    queryset = (
        EventRegistration.objects.filter(event=event, created_at__lte=cutoff)
        .select_related("ticket")
        .order_by("created_at", "pk")
    )
    return list(queryset)


def _record_empty_append(event: Event, *, cursor_from=None, cursor_to=None) -> None:
    cursor_to = cursor_to or timezone.now()
    Event.objects.filter(pk=event.pk).update(
        registration_sheet_synced_at=cursor_to,
        registration_sheet_sync_error="",
        updated_at=timezone.now(),
    )
    RegistrationSheetSyncLog.objects.create(
        event=event,
        sync_type=RegistrationSheetSyncLog.SyncType.APPEND,
        status=RegistrationSheetSyncLog.Status.SUCCESS,
        rows_written=0,
        cursor_from=cursor_from,
        cursor_to=cursor_to,
        selected_registration_ids=[],
    )


def _record_append_success(
    event: Event,
    *,
    row_count: int,
    total_count: int,
    cursor_from,
    cursor_to,
    selected_registration_ids: list[str],
) -> None:
    Event.objects.filter(pk=event.pk).update(
        registration_sheet_sync_count=total_count,
        registration_sheet_synced_at=cursor_to,
        registration_sheet_sync_error="",
        updated_at=timezone.now(),
    )
    event.refresh_from_db(fields=["registration_sheet_sync_count", "registration_sheet_synced_at"])
    RegistrationSheetSyncLog.objects.create(
        event=event,
        sync_type=RegistrationSheetSyncLog.SyncType.APPEND,
        status=RegistrationSheetSyncLog.Status.SUCCESS,
        rows_written=row_count,
        cursor_from=cursor_from,
        cursor_to=cursor_to,
        selected_registration_ids=selected_registration_ids,
    )


def _record_append_exception(
    event_id: str,
    exc: Exception,
    *,
    cursor_from=None,
    cursor_to=None,
    selected_registration_ids: list[str] | None = None,
) -> None:
    logger.exception("Batch sheet sync failed for event %s.", event_id)
    try:
        event = Event.objects.get(pk=event_id)
        record_sync_failure(
            event,
            str(exc),
            sync_type=RegistrationSheetSyncLog.SyncType.APPEND,
            rows_written=0,
            cursor_from=cursor_from,
            cursor_to=cursor_to,
            selected_registration_ids=selected_registration_ids,
        )
    except Exception:
        logger.exception("Failed to record sync failure for event %s.", event_id)
