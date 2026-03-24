"""Google Sheets API client — account-based authentication with read+write support."""

import json
import logging

import httplib2
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

SHEETS_SCOPES = ("https://www.googleapis.com/auth/spreadsheets",)


class GoogleSheetsConfigError(RuntimeError):
    """Raised when Google Sheets credentials are misconfigured."""


def _build_client(credentials_json: str, scopes: tuple[str, ...] = SHEETS_SCOPES):
    """Build a Sheets v4 client from service account JSON."""
    try:
        credentials_info = json.loads(credentials_json)
    except json.JSONDecodeError as exc:
        raise GoogleSheetsConfigError("Service account JSON is not valid JSON.") from exc

    try:
        credentials = Credentials.from_service_account_info(credentials_info, scopes=list(scopes))
    except Exception as exc:  # noqa: BLE001
        raise GoogleSheetsConfigError("Failed to build Google service account credentials.") from exc

    http = httplib2.Http(timeout=15)
    return build("sheets", "v4", credentials=credentials, http=http, cache_discovery=False)


def get_client_for_account(account):
    """
    Build a Sheets client from a SheetsAccount instance.

    Marks the account as used after building the client.
    On failure, records the error on the account.
    """
    try:
        client = _build_client(account.service_account_json)
        account.mark_used()
        return client
    except Exception as exc:
        account.mark_used(error=str(exc))
        raise


def fetch_raw_values(account, spreadsheet_id: str, range_ref: str) -> list[list[object]]:
    """Fetch raw values from a Google Sheets range using the given account."""
    client = get_client_for_account(account)
    response = client.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=range_ref).execute()
    return response.get("values", [])


def write_values(account, spreadsheet_id: str, range_ref: str, values: list[list[str]]) -> dict:
    """Write a 2D list of values to a Google Sheets range."""
    client = get_client_for_account(account)
    body = {"values": values}
    response = (
        client.spreadsheets()
        .values()
        .update(
            spreadsheetId=spreadsheet_id,
            range=range_ref,
            valueInputOption="RAW",
            body=body,
        )
        .execute()
    )
    return response


def clear_range(account, spreadsheet_id: str, range_ref: str) -> dict:
    """Clear all values in a Google Sheets range."""
    client = get_client_for_account(account)
    response = client.spreadsheets().values().clear(spreadsheetId=spreadsheet_id, range=range_ref, body={}).execute()
    return response


def normalize_values(values: list[list[object]]) -> tuple[list[str], list[list[str]]]:
    """Normalize raw sheet values into (headers, rows) with consistent column counts."""
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

    # Remove trailing empty rows
    while rows and not any(cell.strip() for cell in rows[-1]):
        rows.pop()

    return headers, rows
