"""Current-semester projects (event CurrentProjects) for the projects app, each matched to its archive project.

Current Projects and Presenting Teams link each team to its event CurrentProject id. Those ids are not archive
ids, and the SPA only finds them in the live schedule, so a link copied last semester stopped resolving once a
new schedule went live. The detail endpoint falls back to this lookup: the team's archive project once the
past-project sheet has imported its semester, otherwise the CurrentProject itself (for a team the schedule only
listed, its row in the schedule it presents in: apps.event.services.current_projects.find_current_projects).
/projects/all/, past-project shares and AI search read current projects through here too, by id or as the active
schedule's: this module is the only one of the projects app that reads the event app.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from apps.projects.models import Project

if TYPE_CHECKING:
    from apps.event.services.current_projects import CurrentProjectReference

_TERM_RE = re.compile(r"^(\d{4})-(\d)\s")
_DIGITS_RE = re.compile(r"\d+", re.ASCII)


@dataclass(frozen=True)
class CurrentProjectLink:
    # The archive project of the same semester, class and Team# (and title, for a team without a slot), if any.
    archived: Project | None
    # The CurrentProject in the shape of the project detail endpoint.
    detail: dict
    # The team's flag on Presenting Teams (False for a team the schedule only lists).
    is_presenting: bool


def _team_key(class_code: str, team_number: str) -> tuple[str, str]:
    """Class and Team# as both apps mean them: ("CAP", "7") for "CAP" / "CAP07", "cap" / "07" or "CAP" / "7".

    The event sync normalises the class ("EngSL" is stored as "ENGSL"), the 2021 archive prefixes the Team# with
    it ("CAP01"), and a sheet may pad the number ("07").
    """
    class_key = "".join(character for character in class_code.upper() if character.isalnum())
    team = team_number.strip().upper()
    if class_key and team.startswith(class_key) and _DIGITS_RE.fullmatch(team[len(class_key) :]):
        team = team[len(class_key) :]
    if _DIGITS_RE.fullmatch(team):
        team = team.lstrip("0") or "0"
    return class_key, team


def _title_key(title: str) -> str:
    return " ".join(title.split()).casefold()


def _archive_match(reference: CurrentProjectReference, semester_teams: dict) -> Project | None:
    project = reference.project
    candidates = semester_teams.get(_team_key(project.class_code, project.team_number), [])
    if reference.track is None:
        # A row without a slot may list a team of another semester (Track "(Fall)"), and team numbers are reused
        # every semester, so this semester's Team# alone can name another team: the title must match too. The slot
        # decides, not is_presenting: admins toggle that flag to show or hide a team, which says nothing about its
        # semester.
        title = _title_key(project.project_title)
        candidates = [candidate for candidate in candidates if _title_key(candidate.project_title) == title]
    return candidates[0] if candidates else None


def _semester_teams(year: int, season: int) -> dict:
    """A published semester's archive projects by team key, each team's sheet rows first (one query)."""
    teams = defaultdict(list)
    projects = Project.objects.filter(semester__is_published=True, semester__year=year, semester__season=season)
    for project in projects.select_related("semester").order_by("-source", "pk"):
        teams[_team_key(project.class_code, project.team_number)].append(project)
    return teams


def _archived_projects(references: Iterable[CurrentProjectReference]) -> dict:
    """Each reference's archive project (or None), by CurrentProject id: one query for each term among them."""
    by_term = defaultdict(dict)
    for reference in references:
        project = reference.project
        match = _TERM_RE.match(reference.term)
        if match and _team_key(project.class_code, project.team_number)[1]:
            by_term[(int(match.group(1)), int(match.group(2)))][project.pk] = reference
    archived = {}
    for (year, season), term_references in by_term.items():
        semester_teams = _semester_teams(year, season)
        for project_id, reference in term_references.items():
            archived[project_id] = _archive_match(reference, semester_teams)
    return archived


def _link(reference: CurrentProjectReference, archived: Project | None) -> CurrentProjectLink:
    project = reference.project
    return CurrentProjectLink(
        archived=archived,
        detail={
            "id": str(project.pk),
            "project_title": project.project_title,
            "team_name": project.team_name,
            "team_number": project.team_number,
            "organization": project.organization,
            "industry": project.industry,
            "abstract": project.abstract,
            "student_names": project.student_names,
            "class_code": project.class_code,
            "track": reference.track,
            "presentation_order": reference.order,
            "semester_label": reference.term,
            "catalog": "current",
            "is_presenting": project.is_presenting,
        },
        is_presenting=project.is_presenting,
    )


def resolve_current_project_links(project_ids: Iterable) -> dict[str, CurrentProjectLink]:
    """The projects current-semester links point to, from any schedule, keyed by the id as requested (as text); an id
    that is no CurrentProject is left out. A fixed number of queries, plus one for each term among them."""
    # The event app owns current projects; projects may read them only here (scripts/ci/python_dependencies.toml).
    from apps.event.services.current_projects import find_current_projects

    references = find_current_projects(project_ids)
    archived = _archived_projects(references.values())
    return {key: _link(reference, archived.get(reference.project.pk)) for key, reference in references.items()}


def resolve_current_project_link(project_id) -> CurrentProjectLink | None:
    """The project a current-semester link points to, from any schedule; None when the id is no CurrentProject."""
    return resolve_current_project_links([project_id]).get(str(project_id))


def _team_order(reference: CurrentProjectReference) -> tuple:
    # apps.projects.ordering.team_ordering() in Python: class, then Team# as a number, the raw text breaking ties.
    project = reference.project
    return project.class_code, project.team_number.replace(project.class_code, "").rjust(20, "0"), project.team_number


def active_current_project_links() -> list[CurrentProjectLink]:
    """The active schedule's projects (presenting or only listed) in team_ordering(); [] when no schedule is live."""
    from apps.event.services.current_projects import active_schedule_references

    references = sorted(active_schedule_references(), key=_team_order)
    archived = _archived_projects(references)
    return [_link(reference, archived.get(reference.project.pk)) for reference in references]
