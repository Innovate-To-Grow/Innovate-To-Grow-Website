"""Reading the past-projects sheet: its header map, which rows are importable, and each project's sync key."""

from __future__ import annotations

from typing import Any

from apps.core.utils.text import collapse_whitespace, normalize_paragraphs
from apps.projects.services.sheet_sync.hooks import resolve_project_row

from .shared import PastProjectSyncStats

# Map the legacy Google-Sheet header text to Project field names. `get_all_records()`
# keys each row by the header row text, so we map by header (not by index like the
# CSV importer). "Year-Semester" is consumed separately by resolve_project_row.
COLUMN_MAP = {
    "Class": "class_code",
    "Team#": "team_number",
    "Team Name": "team_name",
    "Project Title": "project_title",
    "Organization": "organization",
    "Industry": "industry",
    "Abstract": "abstract",
    "Student Names": "student_names",
}

# Valid Semester.season values (1=Spring, 2=Fall). Other digits parsed out of the
# "Year-Semester" cell (e.g. a stray "2025-3 Summer") are rejected as unimportable.
_VALID_SEASONS = {1, 2}
_STABLE_KEY_FIELDS = ("semester", "class_code", "team_number")
_MUTABLE_PROJECT_FIELDS = tuple(field for field in COLUMN_MAP.values() if field not in _STABLE_KEY_FIELDS)
# Sheet cells carry double spaces, NBSPs and tabs. Displayed text is tidied; the abstract keeps its paragraphs.
# Class and Team# are only trimmed: they are the sync key, and changing them would re-create the project.
_TEXT_NORMALIZERS = {
    field: normalize_paragraphs if field == "abstract" else collapse_whitespace for field in _MUTABLE_PROJECT_FIELDS
}


def _project_sync_key(fields_or_project) -> tuple:
    """Identity for a sheet-synced project: Year-Semester + Class + Team#."""
    if isinstance(fields_or_project, dict):
        return (
            fields_or_project["semester"].pk,
            fields_or_project["class_code"],
            fields_or_project["team_number"],
        )
    semester_id = fields_or_project.semester_id
    class_code = fields_or_project.class_code
    team_number = fields_or_project.team_number
    return (semester_id, class_code, team_number)


def _importable_row(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Map one sheet record to project fields; None when it cannot be imported."""
    # Normalize header whitespace before mapping: the live sheet has headers
    # like "Project Title " (trailing space), and get_all_records() keys rows
    # by the exact header text, so a strict lookup would silently miss them.
    row = {str(key).strip(): value for key, value in raw.items()}
    mapped = {field: str(row.get(header, "")).strip() for header, field in COLUMN_MAP.items()}
    for field, normalize in _TEXT_NORMALIZERS.items():
        mapped[field] = normalize(mapped[field])
    mapped["Year-Semester"] = str(row.get("Year-Semester", "")).strip()
    resolved = resolve_project_row(mapped, sheet_link=None)
    if resolved is None or resolved["semester"].season not in _VALID_SEASONS or not resolved.get("project_title"):
        return None
    return resolved


def _parse_records(records, stats: PastProjectSyncStats):
    """Importable rows (first occurrence of each project), the keys seen, and the semesters touched."""
    parsed: list[dict[str, Any]] = []
    touched_semester_pks: set[Any] = set()
    seen: set[tuple] = set()
    for raw in records:
        resolved = _importable_row(raw)
        if resolved is None:
            stats.rows_skipped += 1
            continue
        dup_key = _project_sync_key(resolved)
        if dup_key in seen:
            stats.rows_skipped += 1
            continue
        seen.add(dup_key)
        touched_semester_pks.add(resolved["semester"].pk)
        parsed.append(resolved)
    return parsed, seen, touched_semester_pks
