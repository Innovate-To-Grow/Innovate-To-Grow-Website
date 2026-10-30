from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Any

from apps.event.models import CurrentProject, CurrentProjectSchedule

from .parsing import normalize_section_code

# (Team#, title): a CurrentProject's unique key within its schedule.
TeamKey = tuple[str, str]


def _team_key(fields: dict[str, Any]) -> TeamKey:
    return fields["team_number"], fields["project_title"]


def _unclaimed(
    stored: list[CurrentProject],
    matched: dict[TeamKey, CurrentProject],
    class_code: str,
    **values: str,
) -> list[CurrentProject]:
    """The stored rows of the class with these field values that no team of the sheet has taken, oldest first."""
    claimed = {project.pk for project in matched.values()}
    return [
        project
        for project in stored
        if project.pk not in claimed
        and project.class_code == class_code
        and all(getattr(project, name) == value for name, value in values.items())
    ]


def _match_stored_projects(
    config: CurrentProjectSchedule,
    teams: dict[TeamKey, dict[str, Any]],
    unique_titles: set[tuple[str, str]],
) -> dict[TeamKey, CurrentProject]:
    """The stored project each team of the sheet updates, so its id (and every link to it) survives the sync.

    Three passes, each over the stored rows no earlier pass took:
    1. the row with the team's Team# and title (the table's unique key);
    2. when no other team of the sheet has its class and title, the one row of its class with that title: the team
       was renumbered;
    3. the oldest row of its class and Team#: the team's title was edited.
    Every title is matched before any number, so a renumbered team keeps its id even when another team now has its
    old number, whatever order the sheet lists them in. A team none of them matches gets a new row.
    """
    stored = list(CurrentProject.objects.filter(schedule=config).order_by("created_at", "pk"))
    by_key = {(project.team_number, project.project_title): project for project in stored}
    matched = {key: by_key[key] for key in teams if key in by_key}
    for key, fields in teams.items():
        if key not in matched and (fields["class_code"], fields["project_title"]) in unique_titles:
            renumbered = _unclaimed(stored, matched, fields["class_code"], project_title=fields["project_title"])
            if len(renumbered) == 1:
                matched[key] = renumbered[0]
    for key, fields in teams.items():
        if key not in matched:
            same_team = _unclaimed(stored, matched, fields["class_code"], team_number=fields["team_number"])
            if same_team:
                matched[key] = same_team[0]
    return matched


def _save_project(
    config: CurrentProjectSchedule,
    project: CurrentProject | None,
    fields: dict[str, Any],
) -> CurrentProject:
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


def _project_fields(slot: dict[str, Any]) -> dict[str, Any]:
    return {
        "class_code": slot["class_code"],
        "team_number": slot["team_number"].strip(),
        "team_name": slot["team_name"],
        "project_title": slot["project_title"],
        "organization": slot["organization"],
        "industry": slot["industry"],
        "abstract": slot["abstract"],
        "student_names": slot["student_names"],
        "is_presenting": slot["is_presenting"],
    }


def _unique_titles(teams: Iterable[dict[str, Any]]) -> set[tuple[str, str]]:
    """The (class, title) pairs only one team of the sheet has."""
    triples = {(fields["class_code"], fields["project_title"], fields["team_number"]) for fields in teams}
    counts = Counter((class_code, title) for class_code, title, _ in triples)
    return {key for key, count in counts.items() if count == 1}


def sync_projects_from_slots(
    config: CurrentProjectSchedule,
    parsed_slots: list[dict[str, Any]],
) -> tuple[dict[tuple[str, str], CurrentProject], set[Any]]:
    lookup: dict[tuple[str, str], CurrentProject] = {}
    touched_pks: set[Any] = set()
    rows = [(slot, _project_fields(slot)) for slot in _team_slots(parsed_slots)]
    # Rows that repeat a Team# and title are one team: its first row matches it, and every row updates it.
    teams: dict[TeamKey, dict[str, Any]] = {}
    for _, fields in rows:
        teams.setdefault(_team_key(fields), fields)
    projects = _match_stored_projects(config, teams, _unique_titles(fields for _, fields in rows))

    for slot, fields in rows:
        key = _team_key(fields)
        project = _save_project(config, projects.get(key), fields)
        projects[key] = project
        touched_pks.add(project.pk)

        if slot["is_presenting"]:
            lookup_key = (normalize_section_code(slot["class_code"]), fields["team_number"].upper())
            if lookup_key[0] and lookup_key[1] and lookup_key not in lookup:
                lookup[lookup_key] = project

    return lookup, touched_pks
