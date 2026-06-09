from dataclasses import dataclass


class SheetSyncError(Exception):
    """Raised when past-project sheet data cannot be fetched or imported."""


@dataclass
class PastProjectSyncStats:
    rows_read: int = 0
    projects_created: int = 0
    projects_updated: int = 0
    projects_deleted: int = 0
    semesters_touched: int = 0
    rows_skipped: int = 0


def format_sync_stats(stats: "PastProjectSyncStats") -> str:
    """One-line human-readable summary of a sync, shared by the management command and the admin
    "Pull now" action so their wording cannot drift. After the full-replace -> upsert change,
    reporting only ``projects_created`` would show "0" on any steady-state re-sync, so include the
    update and delete counts too."""
    return (
        f"{stats.projects_created} created, {stats.projects_updated} updated, "
        f"{stats.projects_deleted} deleted across {stats.semesters_touched} semester(s); "
        f"{stats.rows_skipped} rows skipped of {stats.rows_read} read."
    )
