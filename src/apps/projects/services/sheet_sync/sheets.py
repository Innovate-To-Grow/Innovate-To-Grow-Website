from __future__ import annotations

from typing import Any

from apps.core.models import GoogleCredentialConfig
from apps.projects.models import PastProjectsSheetConfig

from .shared import SheetSyncError


def fetch_past_project_records() -> list[dict[str, Any]]:
    """Read the configured past-projects worksheet into a list of header-keyed dicts."""
    source = PastProjectsSheetConfig.load()
    if not source or not source.sheet_id or not source.worksheet_name:
        raise SheetSyncError("Past-projects Google Sheet source is not fully configured.")

    credentials = GoogleCredentialConfig.load()
    if not credentials.is_configured:
        raise SheetSyncError("No active Google service account is configured.")

    try:
        import gspread

        client = gspread.service_account_from_dict(credentials.get_credentials_info())
        spreadsheet = client.open_by_key(source.sheet_id)
        worksheet = spreadsheet.worksheet(source.worksheet_name)
    except Exception as exc:
        raise SheetSyncError(f"Unable to open the configured Google Sheet: {exc}") from exc

    try:
        return worksheet.get_all_records()
    except Exception as exc:
        raise SheetSyncError(f"Unable to read past-project worksheet records: {exc}") from exc
