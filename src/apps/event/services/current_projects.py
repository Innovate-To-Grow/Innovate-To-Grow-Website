"""Current-semester projects as the rest of the site sees them: a schedule's term and a project found by its id."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from apps.event.models import CurrentProject, CurrentProjectSchedule, EventScheduleSlot

# /event/projects/ caches the active schedule's projects under this key.
CURRENT_PROJECTS_CACHE_KEY = "event:current-projects"


def predominant_term(labels: Iterable[str]) -> str:
    """The Year-Semester most rows carry ("2026-2 Fall"), or "" when none carries one.

    Only the sheet rows of presenting teams fill in a term, but every team of a schedule belongs to its semester.
    """
    counts = Counter(label for label in labels if label)
    return counts.most_common(1)[0][0] if counts else ""


def schedule_term(config: CurrentProjectSchedule) -> str:
    slots = EventScheduleSlot.objects.filter(track__section__config=config, is_break=False)
    return predominant_term(slots.values_list("year_semester", flat=True))


@dataclass(frozen=True)
class CurrentProjectReference:
    project: CurrentProject
    term: str
    track: int | None
    order: int | None


def find_current_project(project_id) -> CurrentProjectReference | None:
    """The CurrentProject with this id in any schedule (the live one or an earlier semester's), or None."""
    project = CurrentProject.objects.select_related("schedule").filter(pk=project_id).first()
    if project is None:
        return None
    slot = project.schedule_slots.filter(is_break=False).select_related("track").order_by("slot_order").first()
    return CurrentProjectReference(
        project=project,
        term=schedule_term(project.schedule),
        track=slot.track.track_number if slot else None,
        order=slot.slot_order if slot else None,
    )
