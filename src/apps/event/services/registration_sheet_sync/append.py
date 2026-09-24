"""Background compatibility adapter for managed registration reconciliation."""

import logging
import threading
from types import SimpleNamespace

from django.db import close_old_connections

from apps.event.models import Event, RegistrationSheetSyncLog

from .engine import sync_registrations_to_sheet
from .scheduler import job_should_run, schedule_registration_sync

logger = logging.getLogger(__name__)
_sync_timers: dict[str, threading.Timer] = {}
_sync_lock = threading.Lock()


def _flush_pending_sync(event_id: str, *, raise_errors=False, job=None, immediate=False):
    try:
        close_old_connections()
        event = Event.objects.get(pk=event_id)
        if not event.registration_sheet_id:
            return
        sync_type = (
            RegistrationSheetSyncLog.SyncType.FULL
            if immediate or (job is not None and job.payload.get("immediate"))
            else RegistrationSheetSyncLog.SyncType.APPEND
        )
        return sync_registrations_to_sheet(event, job=job, sync_type=sync_type)
    except Exception:
        logger.exception("Registration sheet reconciliation failed for event %s.", event_id)
        if raise_errors:
            raise
    finally:
        close_old_connections()


def _schedule_in_process_sync(event_id: str, delay: float, immediate: bool) -> None:
    """Fallback for installations without the durable worker; the queued job stays as a record."""
    with _sync_lock:
        existing = _sync_timers.pop(event_id, None)
        if existing is not None:
            existing.cancel()
        timer = None
        try:
            timer = threading.Timer(max(0.0, delay), _run_in_process_sync, args=[event_id, immediate])
            timer.daemon = True
            _sync_timers[event_id] = timer
            timer.start()
        except Exception:  # noqa: BLE001 - a best-effort timer must not break the caller.
            if _sync_timers.get(event_id) is timer:
                _sync_timers.pop(event_id, None)
            logger.exception("Unable to start the registration sheet sync timer for event %s", event_id)


def _run_in_process_sync(event_id: str, immediate: bool) -> None:
    with _sync_lock:
        if _sync_timers.get(event_id) is not threading.current_thread():
            # A newer timer replaced this one while it was waking up.
            return
        _sync_timers.pop(event_id, None)
    try:
        close_old_connections()
        should_run = job_should_run(SimpleNamespace(payload={"event_id": event_id, "immediate": immediate}))
    except Exception:
        logger.exception("Unable to check pending registration sheet sync for event %s.", event_id)
        return
    finally:
        close_old_connections()
    if should_run:
        _flush_pending_sync(event_id, immediate=immediate)


__all__ = ["_flush_pending_sync", "schedule_registration_sync"]
