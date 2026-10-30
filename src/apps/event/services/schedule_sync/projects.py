from __future__ import annotations

from collections import Counter
from typing import Any

from apps.event.models import CurrentProject, CurrentProjectSchedule

from .parsing import normalize_section_code


def _existing_project(
    config: CurrentProjectSchedule,
    fields: dict[str, Any],
    touched_pks: set[Any],
    unique_titles: set[tuple[str, str]],
) -> CurrentProject | None:
    """The stored project a sheet row updates, so its id (and every link to it) survives a title edit.

    A row with the same Team# and title (the table's unique key) is reused first. Then, when no other team of the
    sheet has this title, the one unclaimed row of the class with that title: the team was renumbered, and its id
    must not go to the team that now has its old number. Otherwise the team's row — same class and Team# — that no
    other sheet row of this sync has claimed takes the new title.
    """
    schedule_projects = CurrentProject.objects.filter(schedule=config)
    same_title = schedule_projects.filter(
        team_number=fields["team_number"], project_title=fields["project_title"]
    ).first()
    if same_title is not None:
        return same_title
    unclaimed = schedule_projects.filter(class_code=fields["class_code"]).exclude(pk__in=touched_pks)
    if (fields["class_code"], fields["project_title"]) in unique_titles:
        renumbered = list(unclaimed.filter(project_title=fields["project_title"])[:2])
        if len(renumbered) == 1:
            return renumbered[0]
    return unclaimed.filter(team_number=fields["team_number"]).order_by("created_at").first()


def _save_project(
    config: CurrentProjectSchedule,
    fields: dict[str, Any],
    touched_pks: set[Any],
    unique_titles: set[tuple[str, str]],
) -> CurrentProject:
    project = _existing_project(config, fields, touched_pks, unique_titles)
    if project is None:
        return CurrentProject.objects.create(schedule=config, **fields)
    for name, value in fields.items():
        setattr(project, name, value)
    # Already its schedule; caching it lets the save signal check whether that schedule is live without a query.
    project.schedule = config
    project.save()
    return project


def _team_slots(parsed_slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The sheet rows that are teams: not breaks, with a Team# and a title other than "Break"."""
    return [
        slot
        for slot in parsed_slots
        if not slot["is_break"] and slot["team_number"].strip() and slot["project_title"].lower() != "break"
    ]


def _unique_titles(team_slots: list[dict[str, Any]]) -> set[tuple[str, str]]:
    """The (class, title) pairs only one team of the sheet has."""
    teams = {(slot["class_code"], slot["project_title"], slot["team_number"].strip()) for slot in team_slots}
    counts = Counter((class_code, title) for class_code, title, _ in teams)
    return {key for key, count in counts.items() if count == 1}


def sync_projects_from_slots(
    config: CurrentProjectSchedule,
    parsed_slots: list[dict[str, Any]],
) -> tuple[dict[tuple[str, str], CurrentProject], set[Any]]:
    lookup: dict[tuple[str, str], CurrentProject] = {}
    touched_pks: set[Any] = set()
    team_slots = _team_slots(parsed_slots)
    unique_titles = _unique_titles(team_slots)

    for slot in team_slots:
        team_number = slot["team_number"].strip()
        section_code = normalize_section_code(slot["class_code"])
        project = _save_project(
            config,
            {
                "class_code": slot["class_code"],
                "team_number": team_number,
                "team_name": slot["team_name"],
                "project_title": slot["project_title"],
                "organization": slot["organization"],
                "industry": slot["industry"],
                "abstract": slot["abstract"],
                "student_names": slot["student_names"],
                "is_presenting": slot["is_presenting"],
            },
            touched_pks,
            unique_titles,
        )
        touched_pks.add(project.pk)

        if slot["is_presenting"]:
            key = (section_code, team_number.upper())
            if key[0] and key[1] and key not in lookup:
                lookup[key] = project

    return lookup, touched_pks
