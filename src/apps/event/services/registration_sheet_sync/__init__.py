"""Managed export of an event's registrations to a Google Sheet.

``worksheet`` reads and writes the destination, ``plan`` decides what to write, ``sync`` runs a sync (inspect,
write, fresh worksheet, failures, entry points) and ``schedule`` decides when. Callers import from this package.
"""

from .plan.schema import available_registration_fields
from .schedule.batching import schedule_registration_sync
from .sync.append import _flush_pending_sync
from .sync.create import create_registration_worksheet
from .sync.engine import sync_registrations_to_sheet
from .sync.prepare import inspect_registration_sheet
from .worksheet.sheets import GoogleCredentialConfig, RegistrationSyncError, _get_worksheet

DEBOUNCE_SECONDS = 15

__all__ = [
    "DEBOUNCE_SECONDS",
    "GoogleCredentialConfig",
    "RegistrationSyncError",
    "_flush_pending_sync",
    "_get_worksheet",
    "schedule_registration_sync",
    "sync_registrations_to_sheet",
    "inspect_registration_sheet",
    "create_registration_worksheet",
    "available_registration_fields",
]
