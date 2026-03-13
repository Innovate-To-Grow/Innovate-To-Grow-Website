import logging

from django.core.cache import cache

from core.services.google_sheets import GoogleSheetsConfigError
from core.services.google_sheets import fetch_raw_values as _fetch_raw_values
from core.services.google_sheets import normalize_values as _normalize_values

logger = logging.getLogger(__name__)

# Re-export for any existing consumers
__all__ = ["GoogleSheetsConfigError", "fetch_source_data"]


def _parse_current_rows(headers: list[str], rows: list[list[str]], semester_filter: str) -> list[dict]:
    """Parse rows from a current/archive event sheet (12-column layout)."""
    parsed = []
    for row in rows:
        if semester_filter and len(row) > 2 and row[2] != semester_filter:
            continue
        parsed.append(
            {
                "Track": row[0] if len(row) > 0 else "",
                "Order": row[1] if len(row) > 1 else "",
                "Year-Semester": row[2] if len(row) > 2 else "",
                "Class": row[3] if len(row) > 3 else "",
                "Team#": row[4] if len(row) > 4 else "",
                "TeamName": row[5] if len(row) > 5 else "",
                "Project Title": row[6] if len(row) > 6 else "",
                "Organization": row[7] if len(row) > 7 else "",
                "Industry": row[8] if len(row) > 8 else "",
                "Abstract": row[9] if len(row) > 9 else "",
                "Student Names": row[10] if len(row) > 10 else "",
                "NameTitle": row[11] if len(row) > 11 else "",
            }
        )
    return parsed


def _parse_past_rows(headers: list[str], rows: list[list[str]]) -> list[dict]:
    """Parse rows from the past-projects sheet (9-column layout)."""
    parsed = []
    for row in rows:
        parsed.append(
            {
                "Track": "",
                "Order": "",
                "Year-Semester": row[0] if len(row) > 0 else "",
                "Class": row[1] if len(row) > 1 else "",
                "Team#": row[2] if len(row) > 2 else "",
                "TeamName": row[3] if len(row) > 3 else "",
                "Project Title": row[4] if len(row) > 4 else "",
                "Organization": row[5] if len(row) > 5 else "",
                "Industry": row[6] if len(row) > 6 else "",
                "Abstract": row[7] if len(row) > 7 else "",
                "Student Names": row[8] if len(row) > 8 else "",
                "NameTitle": "",
            }
        )
    return parsed


def _parse_track_infos(headers: list[str], rows: list[list[str]]) -> list[dict]:
    """Parse track info rows (3 columns: name, room, zoomLink)."""
    parsed = []
    for row in rows:
        parsed.append(
            {
                "name": row[0] if len(row) > 0 else "",
                "room": row[1] if len(row) > 1 else "",
                "zoomLink": row[2] if len(row) > 2 else "",
            }
        )
    return parsed


def fetch_source_data(source) -> dict:
    """
    Fetch, parse, and cache data for a GoogleSheetSource.

    Returns a dict with slug, title, sheet_type, rows, and track_infos.
    """
    cache_key = f"sheets:{source.slug}:data"

    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # Fetch main sheet data
    raw_values = _fetch_raw_values(source.spreadsheet_id, source.range_a1)
    headers, rows = _normalize_values(raw_values)

    # Parse based on sheet type
    if source.sheet_type == "past-projects":
        parsed_rows = _parse_past_rows(headers, rows)
    else:
        parsed_rows = _parse_current_rows(headers, rows, source.semester_filter)

    # Fetch track info if configured
    track_infos = []
    if source.tracks_sheet_name:
        tracks_sid = source.tracks_spreadsheet_id or source.spreadsheet_id
        track_values = _fetch_raw_values(tracks_sid, source.tracks_sheet_name)
        track_headers, track_rows = _normalize_values(track_values)
        track_infos = _parse_track_infos(track_headers, track_rows)

    payload = {
        "slug": source.slug,
        "title": source.title,
        "sheet_type": source.sheet_type,
        "rows": parsed_rows,
        "track_infos": track_infos,
    }

    cache.set(cache_key, payload, timeout=source.cache_ttl_seconds)
    return payload
