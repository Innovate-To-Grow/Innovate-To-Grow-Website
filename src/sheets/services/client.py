"""Google Sheets API client for fetching spreadsheet data."""

import json
import logging

import httplib2
from django.conf import settings
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)


class GoogleSheetsConfigError(RuntimeError):
    """Raised when Google Sheets credentials or scopes are misconfigured."""


def build_sheets_client_sa(credentials_json: str, scopes: tuple[str, ...]):
    """Build a Sheets client using service account credentials."""
    try:
        credentials_info = json.loads(credentials_json)
    except json.JSONDecodeError as exc:
        raise GoogleSheetsConfigError("GOOGLE_SHEETS_CREDENTIALS_JSON is not valid JSON.") from exc

    try:
        credentials = Credentials.from_service_account_info(credentials_info, scopes=list(scopes))
    except Exception as exc:  # noqa: BLE001
        raise GoogleSheetsConfigError("Failed to build Google service account credentials.") from exc

    http = httplib2.Http(timeout=15)
    return build("sheets", "v4", credentials=credentials, http=http, cache_discovery=False)


def build_sheets_client_key(api_key: str):
    """Build a Sheets client using an API key (public read-only access)."""
    http = httplib2.Http(timeout=15)
    return build("sheets", "v4", developerKey=api_key, http=http, cache_discovery=False)


def get_sheets_client():
    credentials_json = getattr(settings, "GOOGLE_SHEETS_CREDENTIALS_JSON", "")
    api_key = getattr(settings, "GOOGLE_SHEETS_API_KEY", "")

    if credentials_json:
        scopes = tuple(getattr(settings, "GOOGLE_SHEETS_SCOPES", []))
        if not scopes:
            raise GoogleSheetsConfigError("GOOGLE_SHEETS_SCOPES is not configured.")
        return build_sheets_client_sa(credentials_json, scopes)

    if api_key:
        return build_sheets_client_key(api_key)

    raise GoogleSheetsConfigError("Neither GOOGLE_SHEETS_CREDENTIALS_JSON nor GOOGLE_SHEETS_API_KEY is configured.")


def fetch_raw_values(spreadsheet_id: str, range_ref: str) -> list[list[object]]:
    """Fetch raw values from a Google Sheets range."""
    client = get_sheets_client()
    response = client.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=range_ref).execute()
    return response.get("values", [])


def normalize_values(values: list[list[object]]) -> tuple[list[str], list[list[str]]]:
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


def build_sheet_range(sheet_name: str, range_a1: str) -> str:
    cleaned_range = (range_a1 or "").strip()
    if cleaned_range:
        return f"{sheet_name}!{cleaned_range}"
    return sheet_name
