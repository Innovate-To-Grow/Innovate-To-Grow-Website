from __future__ import annotations

from typing import Any

from apps.event.models import CurrentProject, CurrentProjectSchedule

from .parsing import normalize_section_code


def _existing_project(
    config: CurrentProjectSchedule,
    fields: dict[str, Any],
    touched_pks: set[Any],
) -> CurrentProject | None:
    """The stored project a sheet row updates, so its id (and every link to it) survives a title edit.

    A row with the same Team# and title (the table's unique key) is reused first. Otherwise the team's row —
    same class and Team# — that no other sheet row of this sync has claimed takes the new title.
    """
    projects = CurrentProject.objects.filter(schedule=config, team_number=fields["team_number"])
    same_title = projects.filter(project_title=fields["project_title"]).first()
    if same_title is not None:
        return same_title
    return projects.filter(class_code=fields["class_code"]).exclude(pk__in=touched_pks).order_by("created_at").first()


def _save_project(config: CurrentProjectSchedule, fields: dict[str, Any], touched_pks: set[Any]) -> CurrentProject:
    project = _existing_project(config, fields, touched_pks)
    if project is None:
        return CurrentProject.objects.create(schedule=config, **fields)
    for name, value in fields.items():
        setattr(project, name, value)
    project.save()
    return project


def sync_projects_from_slots(
    config: CurrentProjectSchedule,
    parsed_slots: list[dict[str, Any]],
) -> tuple[dict[tuple[str, str], CurrentProject], set[Any]]:
    lookup: dict[tuple[str, str], CurrentProject] = {}
    touched_pks: set[Any] = set()

    for slot in parsed_slots:
        if slot["is_break"]:
            continue
        team_number = slot["team_number"].strip()
        if not team_number:
            continue
        title = slot["project_title"]
        if title.lower() == "break":
            continue

        section_code = normalize_section_code(slot["class_code"])
        project = _save_project(
            config,
            {
                "class_code": slot["class_code"],
                "team_number": team_number,
                "team_name": slot["team_name"],
                "project_title": title,
                "organization": slot["organization"],
                "industry": slot["industry"],
                "abstract": slot["abstract"],
                "student_names": slot["student_names"],
                "is_presenting": slot["is_presenting"],
            },
            touched_pks,
        )
        touched_pks.add(project.pk)

        if slot["is_presenting"]:
            key = (section_code, team_number.upper())
            if key[0] and key[1] and key not in lookup:
                lookup[key] = project

    return lookup, touched_pks
