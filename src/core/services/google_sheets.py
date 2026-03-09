"""
Read/write Google Sheets client for membership data.

This is the single interface through which all Django code accesses the
membership spreadsheet (Members, Logs, Prospects, and per-event worksheets).

Design principles:
  - Sheets is the source of truth; Django reads FROM Sheets and syncs into its DB.
  - All writes also go back to Sheets so the legacy Flask system keeps seeing them.
  - The API client is lazily built and cached for the process lifetime.
  - Every API call goes through _with_backoff(), which retries on HTTP 429/503
    with exponential backoff + jitter — mirroring the old Flask BackoffClient.

Configuration (environment variables, set via src/.env):
  GOOGLE_SHEETS_CREDENTIALS_JSON  — service account JSON as a single-line string
                                    (same var used by the CMS read-only client)
  MEMBERSHIP_SPREADSHEET_ID       — the spreadsheet ID from the URL:
                                    docs.google.com/spreadsheets/d/<ID>/edit

Note: this module uses the full read+write scope
(https://www.googleapis.com/auth/spreadsheets). The CMS read-only client
in pages/services/google_sheets.py uses spreadsheets.readonly — they are
independent and do not share a cached API client.
"""

import json
import logging
import random
import time
from functools import lru_cache
from typing import Any

from django.conf import settings
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

# Full read+write scope — superset of spreadsheets.readonly
_WRITE_SCOPE = "https://www.googleapis.com/auth/spreadsheets"

# Retry / backoff configuration
_MAX_RETRIES = 5
_INITIAL_BACKOFF_SECS = 1.0
_RETRYABLE_STATUSES = {429, 503}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class SheetsError(Exception):
    """Raised when a Sheets operation fails after all retries."""


class SheetsConfigError(SheetsError):
    """Raised when required settings are absent or invalid."""


# ---------------------------------------------------------------------------
# Client construction (cached for the process lifetime)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _cached_client(credentials_json: str):
    """Build a Sheets API v4 client. Cached so it is only built once per process."""
    try:
        info = json.loads(credentials_json)
    except json.JSONDecodeError as exc:
        raise SheetsConfigError("GOOGLE_SHEETS_CREDENTIALS_JSON is not valid JSON.") from exc

    try:
        creds = Credentials.from_service_account_info(info, scopes=[_WRITE_SCOPE])
    except Exception as exc:  # noqa: BLE001
        raise SheetsConfigError("Failed to build Google service account credentials.") from exc

    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def _get_client():
    credentials_json = getattr(settings, "GOOGLE_SHEETS_CREDENTIALS_JSON", "")
    if not credentials_json:
        raise SheetsConfigError("GOOGLE_SHEETS_CREDENTIALS_JSON is not configured.")
    return _cached_client(credentials_json)


def _get_spreadsheet_id() -> str:
    sid = getattr(settings, "MEMBERSHIP_SPREADSHEET_ID", "")
    if not sid:
        raise SheetsConfigError(
            "MEMBERSHIP_SPREADSHEET_ID is not configured. "
            "Set it to the ID from the spreadsheet URL."
        )
    return sid


# ---------------------------------------------------------------------------
# Retry with exponential backoff
# ---------------------------------------------------------------------------


def _with_backoff(fn):
    """
    Call fn() and retry on HTTP 429 / 503 with exponential backoff + jitter.

    Mirrors the behaviour of gspread's BackoffClient used in the old Flask system.
    Raises SheetsError after _MAX_RETRIES failed attempts.
    """
    backoff = _INITIAL_BACKOFF_SECS
    for attempt in range(_MAX_RETRIES):
        try:
            return fn()
        except HttpError as exc:
            status = int(exc.resp.status)
            if status in _RETRYABLE_STATUSES and attempt < _MAX_RETRIES - 1:
                sleep_for = backoff + random.uniform(0, 0.5)
                logger.warning(
                    "Sheets API rate limit (HTTP %d); retry %d/%d in %.1fs",
                    status,
                    attempt + 1,
                    _MAX_RETRIES,
                    sleep_for,
                )
                time.sleep(sleep_for)
                backoff *= 2
            else:
                raise SheetsError(
                    f"Sheets API error (HTTP {status}) after {attempt + 1} attempt(s)."
                ) from exc


# ---------------------------------------------------------------------------
# Internal utilities
# ---------------------------------------------------------------------------


def _col_letter(col: int) -> str:
    """
    Convert a 1-based column index to an A1-notation letter string.

    Examples: 1 → "A", 26 → "Z", 27 → "AA", 28 → "AB".
    """
    result = ""
    while col > 0:
        col, remainder = divmod(col - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _serialize_value(value: Any) -> Any:
    """Return a Sheets-safe representation of a Python value."""
    if value is None:
        return ""
    return value  # numbers, bools, and strings are all accepted by USER_ENTERED


def _serialize_row(values: list[Any]) -> list[Any]:
    return [_serialize_value(v) for v in values]


# ---------------------------------------------------------------------------
# Public read API
# ---------------------------------------------------------------------------


def get_all_records(worksheet_name: str) -> list[dict[str, Any]]:
    """
    Return all data rows as a list of dicts, each augmented with a 'Row' key
    (1-based spreadsheet row number, so row 2 = index 0 in the returned list).

    Equivalent to gspread's get_all_records() combined with the Row augmentation
    from the old Flask get_wks_records() helper.
    """
    client = _get_client()
    spreadsheet_id = _get_spreadsheet_id()

    response = _with_backoff(
        lambda: client.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=worksheet_name)
        .execute()
    )
    values = response.get("values", [])

    if not values:
        return []

    headers = [str(h) for h in values[0]]
    records = []
    for row_idx, row in enumerate(values[1:], start=2):
        padded = [str(cell) for cell in row] + [""] * max(0, len(headers) - len(row))
        record = dict(zip(headers, padded))
        record["Row"] = row_idx
        records.append(record)
    return records


def get_column_map(worksheet_name: str) -> dict[str, int]:
    """
    Return a dict mapping each column header → 1-based column index.

    Equivalent to the old Flask get_wks_columns() helper.
    """
    client = _get_client()
    spreadsheet_id = _get_spreadsheet_id()

    response = _with_backoff(
        lambda: client.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=f"{worksheet_name}!1:1")
        .execute()
    )
    header_row = response.get("values", [[]])[0] if response.get("values") else []
    return {str(h): i + 1 for i, h in enumerate(header_row)}


def get_column_values(worksheet_name: str, col: int) -> list[str]:
    """
    Return all values in a 1-based column as a flat list of strings (including header).

    Equivalent to gspread's col_values().
    """
    client = _get_client()
    spreadsheet_id = _get_spreadsheet_id()
    col_letter = _col_letter(col)

    response = _with_backoff(
        lambda: client.spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id,
            range=f"{worksheet_name}!{col_letter}:{col_letter}",
        )
        .execute()
    )
    return [str(row[0]) if row else "" for row in response.get("values", [])]


def get_row_values(worksheet_name: str, row: int) -> list[str]:
    """
    Return all values in a 1-based row as a flat list of strings.

    Equivalent to gspread's row_values().
    """
    client = _get_client()
    spreadsheet_id = _get_spreadsheet_id()

    response = _with_backoff(
        lambda: client.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=f"{worksheet_name}!{row}:{row}")
        .execute()
    )
    rows = response.get("values", [[]])
    return [str(cell) for cell in (rows[0] if rows else [])]


def find_row(worksheet_name: str, query: str, col: int = 1) -> int | None:
    """
    Return the 1-based row number of the first cell in `col` that equals `query`.
    Returns None if not found.

    Equivalent to gspread's worksheet.find(query, in_column=col).row.
    """
    values = get_column_values(worksheet_name, col)
    for row_idx, val in enumerate(values, start=1):
        if val == query:
            return row_idx
    return None


# ---------------------------------------------------------------------------
# Public write API
# ---------------------------------------------------------------------------


def append_row(worksheet_name: str, values: list[Any]) -> None:
    """
    Append a row to the end of the worksheet.

    Equivalent to gspread's worksheet.append_row(values).
    """
    client = _get_client()
    spreadsheet_id = _get_spreadsheet_id()
    body = {"values": [_serialize_row(values)]}

    _with_backoff(
        lambda: client.spreadsheets()
        .values()
        .append(
            spreadsheetId=spreadsheet_id,
            range=worksheet_name,
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body,
        )
        .execute()
    )


def update_cell(worksheet_name: str, row: int, col: int, value: Any) -> None:
    """
    Update a single cell (1-based row and col).

    Equivalent to gspread's worksheet.update_cell(row, col, value).
    """
    update_cells(worksheet_name, [(row, col, value)])


def update_cells(worksheet_name: str, updates: list[tuple[int, int, Any]]) -> None:
    """
    Batch-update a set of cells in one API call.

    Each item in `updates` is a (row, col, value) tuple with 1-based coordinates.
    Equivalent to gspread's worksheet.update_cells(cell_list) with Cell objects.
    """
    if not updates:
        return

    client = _get_client()
    spreadsheet_id = _get_spreadsheet_id()

    data = [
        {
            "range": f"{worksheet_name}!{_col_letter(col)}{row}",
            "values": [[_serialize_value(value)]],
        }
        for row, col, value in updates
    ]
    body = {"valueInputOption": "USER_ENTERED", "data": data}

    _with_backoff(
        lambda: client.spreadsheets()
        .values()
        .batchUpdate(spreadsheetId=spreadsheet_id, body=body)
        .execute()
    )
