"""The rows of a shared curation, taken from the published catalog rather than from what a client sent.

A share is a public page on the site, so its rows must say what the archive says. On every write each row is
rebuilt from the published project it names; a row naming no published project is refused, unless the share
already holds it (a project removed from the archive since), and then it is kept exactly as stored. Reads show
the catalog's current text for every row that still resolves, which also adds the project id to legacy rows
saved before rows carried one.
"""

from __future__ import annotations

import re
import uuid

from apps.projects.models import Project

# The fields a stored row carries, as the frontend's ProjectGridRow names them.
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


class UnknownShareRows(Exception):
    """Raised when submitted rows name no published project and are not already in the share."""

    def __init__(self, count: int):
        super().__init__(count)
        self.count = count


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


def _projects_by_id(rows) -> dict[str, Project]:
    ids = {project_id for row in rows if row.get("id") for project_id in [_uuid_or_none(row["id"])] if project_id}
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


def catalog_row(project: Project) -> dict:
    """A share row as the archive has it, in the shape the past-projects pages build their rows."""
    return {
        "id": str(project.pk),
        # The pages show "2025 Spring", not the sortable "2025-1 Spring" label.
        "semester_label": re.sub(r"^(\d{4})-[12]\s+", r"\1 ", project.semester.label),
        "class_code": project.class_code,
        "team_number": project.team_number,
        "team_name": project.team_name,
        "project_title": project.project_title,
        "organization": project.organization,
        "industry": project.industry,
        "abstract": project.abstract,
        "student_names": project.student_names,
        # Archive projects have no presenting flag; the pages give their rows "".
        "is_presenting": "",
    }


class _Catalog:
    """The published projects a list of rows names, by id and (for rows without one) by stable key."""

    def __init__(self, rows):
        self._by_id = _projects_by_id(rows)
        self._by_key = _projects_by_stable_key(rows)

    def project_for(self, row) -> Project | None:
        if row.get("id"):
            return self._by_id.get(_uuid_or_none(row["id"]))
        key = _row_stable_key(row)
        return self._by_key.get(key) if key is not None else None


def _row_identities(row):
    """How a submitted row is recognised as one the share stores: its id, else its stable key; or its content."""
    if row.get("id"):
        identities = [("id", _uuid_or_none(row["id"]) or str(row["id"]))]
    else:
        key = _row_stable_key(row)
        identities = [("key", key)] if key is not None else []
    identities.append(("row", tuple(str(row.get(field) or "") for field in ROW_FIELDS)))
    return identities


def _stored_rows_by_identity(stored_rows) -> dict:
    by_identity = {}
    for row in stored_rows:
        for identity in _row_identities(row):
            by_identity.setdefault(identity, row)
    return by_identity


def rebuild_share_rows(submitted_rows, stored_rows=()) -> list[dict]:
    """The rows to store for ``submitted_rows``: each from the catalog, or as ``stored_rows`` already hold it.

    Raises :class:`UnknownShareRows` when a row names no published project and the share does not hold it.
    """
    catalog = _Catalog(submitted_rows)
    stored = _stored_rows_by_identity(stored_rows)
    rebuilt = []
    unknown = 0
    for row in submitted_rows:
        project = catalog.project_for(row)
        if project is not None:
            rebuilt.append(catalog_row(project))
            continue
        kept = next((stored[identity] for identity in _row_identities(row) if identity in stored), None)
        if kept is None:
            unknown += 1
        else:
            rebuilt.append(dict(kept))
    if unknown:
        raise UnknownShareRows(unknown)
    return rebuilt


def rows_for_display(stored_rows) -> list[dict]:
    """The stored rows with the catalog's current text wherever a row still names a published project.

    Rows saved before rows carried an id resolve by Year-Semester + Class + Team#; a row that no longer resolves
    is shown as stored. The stored snapshot itself is not changed.
    """
    catalog = _Catalog(stored_rows)
    rows = []
    for row in stored_rows:
        project = catalog.project_for(row)
        rows.append(catalog_row(project) if project is not None else dict(row))
    return rows
