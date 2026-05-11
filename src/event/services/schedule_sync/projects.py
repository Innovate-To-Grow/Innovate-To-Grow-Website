from __future__ import annotations

from typing import Any

from event.models import CurrentProject, CurrentProjectSchedule

from .parsing import normalize_section_code


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
        project, _ = CurrentProject.objects.update_or_create(
            schedule=config,
            team_number=team_number,
            project_title=title,
            defaults={
                "class_code": slot["class_code"],
                "team_name": slot["team_name"],
                "organization": slot["organization"],
                "industry": slot["industry"],
                "abstract": slot["abstract"],
                "student_names": slot["student_names"],
                "is_presenting": slot["is_presenting"],
            },
        )
        touched_pks.add(project.pk)

        if slot["is_presenting"]:
            key = (section_code, team_number.upper())
            if key[0] and key[1] and key not in lookup:
                lookup[key] = project

    return lookup, touched_pks
