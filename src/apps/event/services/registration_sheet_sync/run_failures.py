"""What a sheet-sync run has done so far, and how a failed run is recorded."""

from dataclasses import dataclass

from .logs import record_sync_failure
from .scheduler import fail_sync
from .sheets import RegistrationSyncConflict


def _rows_written(plan, provider_write_completed: bool) -> int:
    if not provider_write_completed:
        return 0
    return sum(plan.counts[key] for key in ("added", "updated", "deleted"))


def _record_failed_run(event, exc, *, generation, sync_type, started_at, rows_written, details, conflicts=0, **log):
    """Mark the generation failed (blocked on a conflict) and log the failed run with its details."""
    fail_sync(event.pk, generation, str(exc), blocked=isinstance(exc, RegistrationSyncConflict), conflicts=conflicts)
    record_sync_failure(
        event,
        str(exc),
        sync_type=sync_type,
        rows_written=rows_written,
        cursor_to=started_at,
        details={"generation": generation, "sheet_id": event.registration_sheet_id, **details},
        **log,
    )


@dataclass
class _RunState:
    """What a run has done so far; the failure record reports it."""

    event: object
    plan: object = None
    snapshot: object = None
    backup: object = None
    new_worksheet: object = None
    provider_write_completed: bool = False
