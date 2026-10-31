"""Current-semester projects as the rest of the site sees them: found by their ids, or the active schedule's."""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from django.db.models import Q

from apps.event.models import CurrentProject, EventScheduleSlot

# /event/projects/ caches the active schedule's projects under this key.
CURRENT_PROJECTS_CACHE_KEY = "event:current-projects"


def predominant_term(labels: Iterable[str]) -> str:
    """The Year-Semester most rows carry ("2026-2 Fall"), or "" when none carries one.

    Only the sheet rows of presenting teams fill in a term, but every team of a schedule belongs to its semester.
    """
    counts = Counter(label for label in labels if label)
    return counts.most_common(1)[0][0] if counts else ""


def _schedule_terms(schedule_ids: Iterable) -> dict:
    """Each schedule's term (:func:`predominant_term` of its slots), by schedule id, from one query."""
    labels = defaultdict(list)
    # The slots' default order, as each schedule's own query would read them: it breaks a tie between two terms.
    slots = EventScheduleSlot.objects.filter(track__section__config__in=schedule_ids, is_break=False)
    for schedule_id, label in slots.values_list("track__section__config_id", "year_semester"):
        labels[schedule_id].append(label)
    return {schedule_id: predominant_term(labels[schedule_id]) for schedule_id in schedule_ids}


@dataclass(frozen=True)
class CurrentProjectReference:
    project: CurrentProject
    term: str
    track: int | None
    order: int | None


def _team_records(projects: list[CurrentProject]) -> dict:
    """Each project's team record, by project id: the project itself, unless an earlier schedule only listed the team.

    A schedule also lists teams that present in another semester (Track "(Fall)"): such a row has no slot and only
    what the sheet held before the team handed anything in, and the row of the schedule the team presents in (same
    class, Team# and title) carries its students and slot. Team numbers are reused every semester, so the title
    must match too. "Only listed" is read from is_presenting, which the sync sets from Track; the archive match in
    apps.projects.services.current_project_links goes by the slot instead (see docs/api/projects.md).
    """
    records = {project.pk: project for project in projects}
    listed = [project for project in projects if not (project.is_presenting or project.schedule.is_active)]
    if not listed:
        return records
    candidates = defaultdict(list)
    rows = (
        CurrentProject.objects.select_related("schedule")
        .filter(team_number__in={p.team_number for p in listed}, project_title__in={p.project_title for p in listed})
        .filter(Q(is_presenting=True) | Q(schedule__is_active=True))
        .order_by("-is_presenting", "-schedule__is_active", "-schedule__created_at")
    )
    for row in rows:
        candidates[(row.class_code, row.team_number, row.project_title)].append(row)
    for project in listed:
        same_team = candidates[(project.class_code, project.team_number, project.project_title)]
        records[project.pk] = next((row for row in same_team if row.schedule_id != project.schedule_id), project)
    return records


def _first_slots(project_ids: Iterable) -> dict:
    """Each project's first slot that is not a break (lowest Order, then lowest Track), by project id."""
    slots = (
        EventScheduleSlot.objects.filter(project__in=project_ids, is_break=False)
        .select_related("track")
        .order_by("slot_order", "track__track_number", "pk")
    )
    first = {}
    for slot in slots:
        first.setdefault(slot.project_id, slot)
    return first


def _references(projects: list[CurrentProject]) -> dict[uuid.UUID, CurrentProjectReference]:
    """Each team record with its schedule's term and its slot, by project id: one query for each."""
    slots = _first_slots([project.pk for project in projects])
    terms = _schedule_terms({project.schedule_id for project in projects})
    references = {}
    for project in projects:
        slot = slots.get(project.pk)
        references[project.pk] = CurrentProjectReference(
            project=project,
            term=terms[project.schedule_id],
            track=slot.track.track_number if slot else None,
            order=slot.slot_order if slot else None,
        )
    return references


def _parsed_ids(project_ids: Iterable) -> dict[str, uuid.UUID]:
    """The requested ids that are UUIDs, keyed by the id as requested (as text)."""
    parsed = {}
    for project_id in project_ids:
        try:
            parsed[str(project_id)] = uuid.UUID(str(project_id))
        except ValueError:
            continue
    return parsed


def find_current_projects(project_ids: Iterable) -> dict[str, CurrentProjectReference]:
    """The CurrentProjects with these ids in any schedule (the live one or an earlier semester's), keyed by the id as
    requested (as text); an id that is no CurrentProject is left out. Three or four queries, however many ids."""
    requested = _parsed_ids(project_ids)
    if not requested:
        return {}
    projects = list(CurrentProject.objects.select_related("schedule").filter(pk__in=set(requested.values())))
    records = _team_records(projects)
    references = _references(list({record.pk: record for record in records.values()}.values()))
    return {key: references[records[pk].pk] for key, pk in requested.items() if pk in records}


def find_current_project(project_id) -> CurrentProjectReference | None:
    """The CurrentProject with this id in any schedule (the live one or an earlier semester's), or None."""
    return find_current_projects([project_id]).get(str(project_id))


def active_schedule_references() -> list[CurrentProjectReference]:
    """Every project of the active schedule, presenting or only listed, with the schedule's term; [] when none is live.

    The live schedule holds its teams' records (see :func:`_team_records`), so each project is its own reference.
    """
    projects = list(
        CurrentProject.objects.select_related("schedule")
        .filter(schedule__is_active=True)
        .order_by("class_code", "team_number", "pk")
    )
    if not projects:
        return []
    references = _references(projects)
    return [references[project.pk] for project in projects]
