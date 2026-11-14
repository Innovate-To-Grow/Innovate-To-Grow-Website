"""Matching a share row to its published catalog project (by id, or by Year-Semester + Class + Team#), and the
row the catalog gives for it."""

from __future__ import annotations

import re
import uuid

from apps.projects.models import Project
from apps.projects.services.catalog.current_project_links import CurrentProjectLink, resolve_current_project_links

# The fields a stored row carries, as the frontend's ProjectGridRow names them. They are also what a row's content
# identity reads (_row_identities), so `catalog`, which every rebuilt row carries as well, is left out.
ROW_FIELDS = (
    "id",
    "semester_label",
    "class_code",
    "team_number",
    "team_name",
    "project_title",
    "organization",
    "industry",
    "abstract",
    "student_names",
    "is_presenting",
)
# What a row copies from its project as it is, archive or current.
_TEXT_FIELDS = tuple(field for field in ROW_FIELDS if field not in {"id", "semester_label", "is_presenting"})


def _normalized_text_key(value):
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _semester_label_key(value):
    label = (value or "").strip()
    match = re.fullmatch(r"(\d{4})(?:-\d+)?\s+(.+)", label)
    if not match:
        return None
    year, season_name = match.groups()
    normalized_season = _normalized_text_key(season_name)
    return (year, normalized_season) if normalized_season else None


def _row_stable_key(row):
    """Year-Semester + Class + Team#: what identifies a project in the sheets, and in rows saved without an id."""
    semester_key = _semester_label_key(row.get("semester_label"))
    class_code = (row.get("class_code") or "").strip()
    team_number = (row.get("team_number") or "").strip()
    if semester_key is None or not class_code or not team_number:
        return None
    return (*semester_key, class_code, team_number)


def _project_stable_key(project):
    return (
        str(project.semester.year),
        _normalized_text_key(project.semester.get_season_display()),
        project.class_code.strip(),
        project.team_number.strip(),
    )


def _published_projects():
    return Project.objects.filter(semester__is_published=True).select_related("semester")


def _uuid_or_none(value):
    try:
        return str(uuid.UUID(str(value)))
    except ValueError:
        return None


def _row_id(row):
    """The project id a row names (canonical when it is a UUID), or None for a row without one."""
    return (_uuid_or_none(row["id"]) or str(row["id"])) if row.get("id") else None


def _projects_by_id(ids) -> dict[str, Project]:
    if not ids:
        return {}
    return {str(project.pk): project for project in _published_projects().filter(pk__in=ids)}


def _projects_by_stable_key(rows) -> dict[tuple, Project]:
    keys = {key for row in rows if not row.get("id") for key in [_row_stable_key(row)] if key is not None}
    if not keys:
        return {}
    candidates = _published_projects().filter(
        semester__year__in={int(key[0]) for key in keys},
        class_code__in={key[2] for key in keys},
        team_number__in={key[3] for key in keys},
    )
    projects = {}
    # A sheet-synced row wins over a manual one with the same key, then the oldest.
    for project in candidates.order_by("-source", "pk"):
        projects.setdefault(_project_stable_key(project), project)
    return {key: project for key, project in projects.items() if key in keys}


def _display_term(label: str) -> str:
    # The pages show "2025 Spring", not the sortable "2025-1 Spring" label.
    return re.sub(r"^(\d{4})-[12]\s+", r"\1 ", label)


def catalog_row(project: Project) -> dict:
    """A share row as the archive has it, in the shape the past-projects pages build their rows."""
    return {
        "id": str(project.pk),
        "semester_label": _display_term(project.semester.label),
        **{field: getattr(project, field) for field in _TEXT_FIELDS},
        # Archive projects have no presenting flag; the pages give their rows "".
        "is_presenting": "",
        "catalog": "archive",
    }


def current_catalog_row(link: CurrentProjectLink) -> dict:
    """A share row as the event has a current-semester project that the archive does not hold yet.

    The id is the team's record (a team an earlier schedule only listed resolves to the row of the schedule it
    presents in), and the term is its schedule's.
    """
    return {
        "id": link.detail["id"],
        "semester_label": _display_term(link.detail["semester_label"]),
        **{field: link.detail[field] for field in _TEXT_FIELDS},
        # As the pages show a current team's flag.
        "is_presenting": "Yes" if link.is_presenting else "No",
        "catalog": "current",
    }


class _Catalog:
    """The projects a list of rows names: published archive projects by id, then current-semester projects (event
    CurrentProjects of any schedule) by id, and for rows without an id, archive projects by stable key."""

    def __init__(self, rows):
        ids = {project_id for row in rows for project_id in [_uuid_or_none(row.get("id") or "")] if project_id}
        self._by_id = _projects_by_id(ids)
        self._current = resolve_current_project_links(ids - self._by_id.keys())
        self._by_key = _projects_by_stable_key(rows)

    def row_for(self, row) -> dict | None:
        """The row as the catalog has the project ``row`` names, or None when it names none."""
        if not row.get("id"):
            key = _row_stable_key(row)
            project = self._by_key.get(key) if key is not None else None
            return catalog_row(project) if project is not None else None
        project_id = _uuid_or_none(row["id"])
        if project_id in self._by_id:
            return catalog_row(self._by_id[project_id])
        link = self._current.get(project_id)
        if link is None:
            return None
        # A current team the archive has imported since reads as its archive row.
        return catalog_row(link.archived) if link.archived is not None else current_catalog_row(link)
