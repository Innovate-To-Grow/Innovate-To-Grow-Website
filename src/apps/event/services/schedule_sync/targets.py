from __future__ import annotations

from apps.event.models import CurrentProjectSchedule

from .shared import ScheduleSyncError


def resolve_sync_targets(schedule_id: str = "", *, force: bool = False) -> list[CurrentProjectSchedule]:
    """Pick the schedules a ``sync_schedule`` run should consider.

    - ``schedule_id`` targets one row (active or not); unknown ids raise.
    - ``force`` without a target keeps the historical behaviour of manual runs:
      the active schedule only.
    - Otherwise (cron mode) every row is a candidate, active first; the caller
      still gates each one on ``sync_is_due``.
    """
    if schedule_id:
        config = CurrentProjectSchedule.load_by_id(schedule_id)
        if config is None:
            raise ScheduleSyncError(f"No CurrentProjectSchedule found with id '{schedule_id}'.")
        return [config]

    if force:
        config = CurrentProjectSchedule.load()
        return [config] if config else []

    return list(CurrentProjectSchedule.objects.order_by("-is_active", "-created_at"))
