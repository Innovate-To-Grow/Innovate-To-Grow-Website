"""
Row transform hooks for Google Sheets sync.

These hooks are called by the sync engine before FK resolution,
allowing custom parsing of compound values in sheet columns.
"""

import re

from projects.models import Semester

YEAR_SEMESTER_RE = re.compile(r"^(\d{4})-(\d)\s")


def resolve_project_row(raw_row: dict, sheet_link) -> dict | None:
    """
    Transform hook for Project sheet rows.

    Parses the compound "Year-Semester" column (e.g., "2025-2 Fall")
    into a Semester FK instance and injects it into the row dict.

    Returns None to skip the row if Year-Semester is unparseable.
    """
    year_sem_value = raw_row.pop("Year-Semester", "").strip()
    if not year_sem_value:
        return None

    match = YEAR_SEMESTER_RE.match(year_sem_value)
    if not match:
        return None

    year = int(match.group(1))
    season = int(match.group(2))

    semester, _ = Semester.objects.get_or_create(year=year, season=season)
    if not semester.is_published:
        semester.is_published = True
        semester.save(update_fields=["is_published"])

    # Inject the resolved FK instance directly (sync engine will use it as-is)
    raw_row["semester"] = semester
    return raw_row
