from __future__ import annotations

from typing import Any

from core.models import GoogleCredentialConfig
from event.models import CurrentProjectSchedule

from .shared import ScheduleSyncError


def get_worksheet_by_gid(spreadsheet, worksheet_gid: int):
    return next(
        (worksheet for worksheet in spreadsheet.worksheets() if worksheet.id == worksheet_gid),
        None,
    )


def fetch_schedule_sheet_records() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    source = CurrentProjectSchedule.load()
    if not source or not source.sheet_id or not source.tracks_gid or not source.projects_gid:
        raise ScheduleSyncError("Google Sheets source is not fully configured for this event.")

    credentials = GoogleCredentialConfig.load()
    if not credentials.is_configured:
        raise ScheduleSyncError("No active Google service account is configured.")

    try:
        import gspread

        client = gspread.service_account_from_dict(credentials.get_credentials_info())
        spreadsheet = client.open_by_key(source.sheet_id)
        tracks_worksheet = get_worksheet_by_gid(spreadsheet, int(source.tracks_gid))
        projects_worksheet = get_worksheet_by_gid(spreadsheet, int(source.projects_gid))
    except Exception as exc:  # pragma: no cover - exercised by mocked service tests
        raise ScheduleSyncError(f"Unable to open the configured Google Sheet: {exc}") from exc

    if tracks_worksheet is None:
        raise ScheduleSyncError("Schedule tracks worksheet not found.")
    if projects_worksheet is None:
        raise ScheduleSyncError("Schedule projects worksheet not found.")

    try:
        return tracks_worksheet.get_all_records(), projects_worksheet.get_all_records()
    except Exception as exc:  # pragma: no cover - exercised by mocked service tests
        raise ScheduleSyncError(f"Unable to read schedule worksheet records: {exc}") from exc
