"""Keep /projects/<id> links from the current-semester pages working after the semester ends.

Current Projects and Presenting Teams link each team to its event CurrentProject id. Those ids are not archive
ids, and the SPA only finds them in the live schedule, so a link copied last semester stopped resolving once a
new schedule went live. The detail endpoint falls back to this lookup: the team's archive project once the
past-project sheet has imported its semester, otherwise the CurrentProject itself (for a team the schedule only
listed, its row in the schedule it presents in: apps.event.services.current_projects.find_current_project).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from apps.projects.models import Project

_TERM_RE = re.compile(r"^(\d{4})-(\d)\s")


@dataclass(frozen=True)
class CurrentProjectLink:
    # The archive project of the same semester, class and Team#, when the archive has it.
    archived: Project | None
    # The CurrentProject in the shape of the project detail endpoint.
    detail: dict


def _archived_project(project, term: str) -> Project | None:
    match = _TERM_RE.match(term)
    if not match or not project.team_number:
        return None
    return (
        Project.objects.filter(
            semester__is_published=True,
            semester__year=int(match.group(1)),
            semester__season=int(match.group(2)),
            class_code=project.class_code,
            team_number=project.team_number,
        )
        .select_related("semester")
        .order_by("-source", "pk")
        .first()
    )


def resolve_current_project_link(project_id) -> CurrentProjectLink | None:
    """The project a current-semester link points to, from any schedule; None when the id is no CurrentProject."""
    # The event app owns current projects; projects may read them only here (scripts/ci/python_dependencies.toml).
    from apps.event.services.current_projects import find_current_project

    reference = find_current_project(project_id)
    if reference is None:
        return None
    project = reference.project
    return CurrentProjectLink(
        archived=_archived_project(project, reference.term),
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
        },
    )
