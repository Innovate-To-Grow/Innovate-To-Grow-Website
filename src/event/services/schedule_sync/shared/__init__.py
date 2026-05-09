from dataclasses import dataclass


class ScheduleSyncError(Exception):
    """Raised when schedule data cannot be fetched or imported."""


@dataclass
class ScheduleSyncStats:
    sections_created: int = 0
    tracks_created: int = 0
    slots_created: int = 0
    agenda_items_created: int = 0
    unmatched_slots: int = 0
    break_slots: int = 0
