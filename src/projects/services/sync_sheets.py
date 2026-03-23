"""Sync project data from Google Sheets into the projects database."""

import logging
import re

from django.core.cache import cache

from projects.models import Project, Semester
from projects.services.import_excel import _to_int, _to_str
from sheets.services import fetch_raw_values, normalize_values

logger = logging.getLogger(__name__)

YEAR_SEMESTER_RE = re.compile(r"^(\d{4})-(\d)\s")


def _parse_year_semester(value: str) -> tuple[int, int] | None:
    """Parse 'YYYY-N Season' (e.g., '2025-2 Fall') → (year=2025, season=2)."""
    match = YEAR_SEMESTER_RE.match((value or "").strip())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _get_or_create_semester(year: int, season: int, semester_cache: dict, stats: dict) -> "Semester":
    """Get or create a semester, auto-publishing it."""
    key = (year, season)
    if key in semester_cache:
        return semester_cache[key]

    semester, created = Semester.objects.get_or_create(year=year, season=season)
    if not semester.is_published:
        semester.is_published = True
        semester.save(update_fields=["is_published"])
    semester_cache[key] = semester
    if created:
        stats["semesters_created"] += 1
    else:
        stats["semesters_existing"] += 1
    return semester


def sync_from_sheet(spreadsheet_id: str, range_a1: str, sheet_type: str, semester_filter: str = "") -> dict:
    """
    Fetch from Google Sheets and upsert into DB.

    sheet_type: 'current-event', 'archive-event', or 'past-projects'
    semester_filter: optional, e.g. '2025-2 Fall' — only sync rows matching this value
    """
    stats = {
        "semesters_created": 0,
        "semesters_existing": 0,
        "projects_created": 0,
        "projects_updated": 0,
        "rows_skipped": 0,
    }

    raw_values = fetch_raw_values(spreadsheet_id, range_a1)
    _headers, rows = normalize_values(raw_values)

    if not rows:
        return stats

    semester_cache: dict[tuple[int, int], Semester] = {}
    is_current = sheet_type in ("current-event", "archive-event")

    for row in rows:
        if is_current:
            # 12-column layout: Track, Order, Year-Semester, Class, Team#, TeamName,
            #   Project Title, Organization, Industry, Abstract, Student Names, NameTitle
            year_sem_val = row[2] if len(row) > 2 else ""
            class_code = _to_str(row[3] if len(row) > 3 else "")
            team_number = _to_str(row[4] if len(row) > 4 else "")
            team_name = _to_str(row[5] if len(row) > 5 else "")
            project_title = _to_str(row[6] if len(row) > 6 else "")
            organization = _to_str(row[7] if len(row) > 7 else "")
            industry = _to_str(row[8] if len(row) > 8 else "")
            abstract = _to_str(row[9] if len(row) > 9 else "")
            student_names = _to_str(row[10] if len(row) > 10 else "")
            track = _to_int(row[0] if len(row) > 0 else None)
            presentation_order = _to_int(row[1] if len(row) > 1 else None)
        else:
            # 9-column layout: Year-Semester, Class, Team#, TeamName,
            #   Project Title, Organization, Industry, Abstract, Student Names
            year_sem_val = row[0] if len(row) > 0 else ""
            class_code = _to_str(row[1] if len(row) > 1 else "")
            team_number = _to_str(row[2] if len(row) > 2 else "")
            team_name = _to_str(row[3] if len(row) > 3 else "")
            project_title = _to_str(row[4] if len(row) > 4 else "")
            organization = _to_str(row[5] if len(row) > 5 else "")
            industry = _to_str(row[6] if len(row) > 6 else "")
            abstract = _to_str(row[7] if len(row) > 7 else "")
            student_names = _to_str(row[8] if len(row) > 8 else "")
            track = None
            presentation_order = None

        # Apply semester filter
        if semester_filter and year_sem_val.strip() != semester_filter.strip():
            stats["rows_skipped"] += 1
            continue

        # Skip rows without a project title
        if not project_title:
            stats["rows_skipped"] += 1
            continue

        # Parse year-semester
        parsed = _parse_year_semester(year_sem_val)
        if not parsed:
            stats["rows_skipped"] += 1
            continue

        year, season = parsed
        semester = _get_or_create_semester(year, season, semester_cache, stats)

        defaults = {
            "team_name": team_name,
            "project_title": project_title,
            "organization": organization,
            "industry": industry,
            "abstract": abstract,
            "student_names": student_names,
            "track": track,
            "presentation_order": presentation_order,
            "class_code": class_code,
        }

        _, created = Project.objects.update_or_create(
            semester=semester,
            team_number=team_number,
            project_title=project_title,
            defaults=defaults,
        )
        if created:
            stats["projects_created"] += 1
        else:
            stats["projects_updated"] += 1

    # Clear project caches
    cache.delete("projects:current")
    cache.delete("projects:past-all")

    return stats


def sync_all_project_sheets() -> dict:
    """
    Read all active GoogleSheetSource records with project-related sheet_types,
    sync each into the DB. Returns combined stats.
    """
    from sheets.models import GoogleSheetSource

    combined = {
        "semesters_created": 0,
        "semesters_existing": 0,
        "projects_created": 0,
        "projects_updated": 0,
        "rows_skipped": 0,
        "sources_synced": 0,
        "errors": [],
    }

    sources = GoogleSheetSource.objects.filter(
        is_active=True,
        sheet_type__in=("current-event", "past-projects", "archive-event"),
    )

    for source in sources:
        try:
            stats = sync_from_sheet(
                spreadsheet_id=source.spreadsheet_id,
                range_a1=source.range_a1,
                sheet_type=source.sheet_type,
                semester_filter=source.semester_filter,
            )
            for key in (
                "semesters_created",
                "semesters_existing",
                "projects_created",
                "projects_updated",
                "rows_skipped",
            ):
                combined[key] += stats[key]
            combined["sources_synced"] += 1
        except Exception as exc:
            logger.exception("Failed to sync sheet source '%s'", source.slug)
            combined["errors"].append(f"{source.slug}: {exc}")

    return combined
