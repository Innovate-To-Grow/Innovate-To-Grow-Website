"""Background compatibility adapter for managed registration reconciliation."""

import logging

from django.db import close_old_connections

from apps.event.models import Event, RegistrationSheetSyncLog

from .engine import sync_registrations_to_sheet
from .scheduler import schedule_registration_sync

logger = logging.getLogger(__name__)


def _flush_pending_sync(event_id: str, *, raise_errors=False, job=None):
    try:
        close_old_connections()
        event = Event.objects.get(pk=event_id)
        if not event.registration_sheet_id:
            return
        sync_type = (
            RegistrationSheetSyncLog.SyncType.FULL
            if job is not None and job.payload.get("immediate")
            else RegistrationSheetSyncLog.SyncType.APPEND
        )
        return sync_registrations_to_sheet(event, job=job, sync_type=sync_type)
    except Exception:
        logger.exception("Registration sheet reconciliation failed for event %s.", event_id)
        if raise_errors:
            raise
    finally:
        close_old_connections()


__all__ = ["_flush_pending_sync", "schedule_registration_sync"]
