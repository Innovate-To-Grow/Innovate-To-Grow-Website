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
