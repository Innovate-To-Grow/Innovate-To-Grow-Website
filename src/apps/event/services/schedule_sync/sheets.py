from __future__ import annotations

from typing import Any

from apps.core.models import GoogleCredentialConfig
from apps.event.models import CurrentProjectSchedule

from .shared import ScheduleSyncError


def get_worksheet_by_gid(spreadsheet, worksheet_gid: int, worksheets=None):
    """Find a worksheet by gid; pass ``worksheets`` to reuse one ``worksheets()`` API call."""
    if worksheets is None:
        worksheets = spreadsheet.worksheets()
    return next((worksheet for worksheet in worksheets if worksheet.id == worksheet_gid), None)


def fetch_schedule_sheet_records(
    source: CurrentProjectSchedule,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Read the tracks + projects worksheets of ``source``'s own Google Sheet.

    Every CurrentProjectSchedule row (e.g. one per event year) carries its own
    sheet id and worksheet gids, so the caller passes the schedule being synced
    rather than this helper silently resolving the active one.
    """
    # gid 0 is the first worksheet of every spreadsheet, so test for None, not falsiness.
    if not source or not source.sheet_id or source.tracks_gid is None or source.projects_gid is None:
        raise ScheduleSyncError("Google Sheets source is not fully configured for this event.")

    credentials = GoogleCredentialConfig.load()
    if not credentials.is_configured:
        raise ScheduleSyncError("No active Google service account is configured.")

    try:
        import gspread

        client = gspread.service_account_from_dict(credentials.get_credentials_info())
        spreadsheet = client.open_by_key(source.sheet_id)
        worksheets = spreadsheet.worksheets()
        tracks_worksheet = get_worksheet_by_gid(spreadsheet, int(source.tracks_gid), worksheets)
        projects_worksheet = get_worksheet_by_gid(spreadsheet, int(source.projects_gid), worksheets)
    except Exception as exc:
        raise ScheduleSyncError(f"Unable to open the configured Google Sheet: {exc}") from exc

    if tracks_worksheet is None:
        raise ScheduleSyncError("Schedule tracks worksheet not found.")
    if projects_worksheet is None:
        raise ScheduleSyncError("Schedule projects worksheet not found.")

    try:
        return tracks_worksheet.get_all_records(), projects_worksheet.get_all_records()
    except Exception as exc:
        raise ScheduleSyncError(f"Unable to read schedule worksheet records: {exc}") from exc
