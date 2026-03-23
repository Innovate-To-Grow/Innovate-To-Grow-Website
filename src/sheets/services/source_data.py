import logging
import threading

from django.core.cache import cache

from .client import GoogleSheetsConfigError
from .client import fetch_raw_values as _fetch_raw_values
from .client import normalize_values as _normalize_values

logger = logging.getLogger(__name__)

# Re-export for any existing consumers
__all__ = ["GoogleSheetsConfigError", "fetch_source_data"]

# Stale data is kept 6x longer than the fresh TTL so users never see a cold-cache fetch
_STALE_TTL_MULTIPLIER = 6


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


def _build_payload(source) -> dict:
    """Fetch from Google Sheets API and build the parsed payload."""
    raw_values = _fetch_raw_values(source.spreadsheet_id, source.range_a1)
    headers, rows = _normalize_values(raw_values)

    if source.sheet_type == "past-projects":
        parsed_rows = _parse_past_rows(headers, rows)
    else:
        parsed_rows = _parse_current_rows(headers, rows, source.semester_filter)

    track_infos = []
    if source.tracks_sheet_name:
        tracks_sid = source.tracks_spreadsheet_id or source.spreadsheet_id
        track_values = _fetch_raw_values(tracks_sid, source.tracks_sheet_name)
        track_headers, track_rows = _normalize_values(track_values)
        track_infos = _parse_track_infos(track_headers, track_rows)

    return {
        "slug": source.slug,
        "title": source.title,
        "sheet_type": source.sheet_type,
        "rows": parsed_rows,
        "track_infos": track_infos,
    }


def _background_refresh(source, cache_key: str, stale_key: str, ttl: int) -> None:
    """Refresh cache in a background thread."""
    try:
        payload = _build_payload(source)
        cache.set(cache_key, payload, timeout=ttl)
        cache.set(stale_key, payload, timeout=ttl * _STALE_TTL_MULTIPLIER)
    except Exception:  # noqa: BLE001
        logger.warning("Background refresh failed for sheets:%s", source.slug)


def fetch_source_data(source) -> dict:
    """
    Fetch, parse, and cache data for a GoogleSheetSource.

    Uses a stale-while-revalidate strategy:
    - Fresh cache hit → return immediately
    - Stale cache hit → return stale data, trigger background refresh
    - Full miss → synchronous fetch (fallback)
    """
    cache_key = f"sheets:{source.slug}:data"
    stale_key = f"sheets:{source.slug}:stale"
    ttl = source.cache_ttl_seconds

    # 1. Fresh cache → return immediately
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # 2. Stale cache → serve stale, refresh in background
    stale = cache.get(stale_key)
    if stale is not None:
        thread = threading.Thread(
            target=_background_refresh,
            args=(source, cache_key, stale_key, ttl),
            daemon=True,
        )
        thread.start()
        return stale

    # 3. Full miss → synchronous fetch
    payload = _build_payload(source)
    cache.set(cache_key, payload, timeout=ttl)
    cache.set(stale_key, payload, timeout=ttl * _STALE_TTL_MULTIPLIER)
    return payload
