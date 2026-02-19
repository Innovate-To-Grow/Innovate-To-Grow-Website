import json
from functools import lru_cache

from django.conf import settings
from django.core.cache import cache
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build


class GoogleSheetsConfigError(RuntimeError):
    """Raised when Google Sheets credentials or scopes are misconfigured."""


def _build_sheet_range(sheet_name: str, range_a1: str) -> str:
    cleaned_range = (range_a1 or "").strip()
    if cleaned_range:
        return f"{sheet_name}!{cleaned_range}"
    return sheet_name


def _normalize_values(values: list[list[object]]) -> tuple[list[str], list[list[str]]]:
    if not values:
        return [], []

    headers = [str(cell) for cell in values[0]]
    header_len = len(headers)

    rows: list[list[str]] = []
    for value_row in values[1:]:
        row = [str(cell) for cell in value_row]
        if header_len:
            if len(row) < header_len:
                row.extend([""] * (header_len - len(row)))
            elif len(row) > header_len:
                row = row[:header_len]
        rows.append(row)

    while rows and not any(cell.strip() for cell in rows[-1]):
        rows.pop()

    return headers, rows


@lru_cache(maxsize=1)
def _build_sheets_client(credentials_json: str, scopes: tuple[str, ...]):
    try:
        credentials_info = json.loads(credentials_json)
    except json.JSONDecodeError as exc:
        raise GoogleSheetsConfigError("GOOGLE_SHEETS_CREDENTIALS_JSON is not valid JSON.") from exc

    try:
        credentials = Credentials.from_service_account_info(credentials_info, scopes=list(scopes))
    except Exception as exc:  # noqa: BLE001
        raise GoogleSheetsConfigError("Failed to build Google service account credentials.") from exc

    return build("sheets", "v4", credentials=credentials, cache_discovery=False)


def _get_sheets_client():
    credentials_json = getattr(settings, "GOOGLE_SHEETS_CREDENTIALS_JSON", "")
    scopes = tuple(getattr(settings, "GOOGLE_SHEETS_SCOPES", []))

    if not credentials_json:
        raise GoogleSheetsConfigError("GOOGLE_SHEETS_CREDENTIALS_JSON is not configured.")
    if not scopes:
        raise GoogleSheetsConfigError("GOOGLE_SHEETS_SCOPES is not configured.")

    return _build_sheets_client(credentials_json, scopes)


def fetch_sheet_values(google_sheet) -> dict[str, list]:
    """Fetch and cache Google Sheet values as table headers and rows."""
    range_ref = _build_sheet_range(google_sheet.sheet_name, google_sheet.range_a1)
    updated_marker = google_sheet.updated_at.isoformat() if google_sheet.updated_at else "none"
    cache_key = f"google_sheet:{google_sheet.id}:{range_ref}:{updated_marker}"

    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    sheets_client = _get_sheets_client()
    response = (
        sheets_client.spreadsheets()
        .values()
        .get(
            spreadsheetId=google_sheet.spreadsheet_id,
            range=range_ref,
        )
        .execute()
    )

    headers, rows = _normalize_values(response.get("values", []))
    payload = {
        "headers": headers,
        "rows": rows,
    }

    cache.set(cache_key, payload, timeout=google_sheet.cache_ttl_seconds)
    return payload
