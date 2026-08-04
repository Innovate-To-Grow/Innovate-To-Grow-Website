from datetime import UTC, datetime

from apps.core.models import GoogleCredentialConfig
from apps.event.models import Event

from .rows import REGISTRATION_ID_COLUMN

_ID_PROTECTION_DESCRIPTION = "Innovate to Grow application-managed Registration ID"


class RegistrationSyncError(RuntimeError):
    """Raised when registration sheet sync fails."""


def read_sheet_values(worksheet) -> list[list[str]]:
    """Return worksheet values while keeping test doubles and empty sheets safe."""
    values = worksheet.get_all_values()
    if not isinstance(values, list):
        return []
    return [row for row in values if isinstance(row, list)]


def registration_ids_from_values(
    values: list[list[str]],
    *,
    expected_header: list[str] | None = None,
) -> set[str]:
    if not values:
        return set()
    header = values[0]
    if (
        REGISTRATION_ID_COLUMN not in header
        or header.count(REGISTRATION_ID_COLUMN) != 1
        or header[-1] != REGISTRATION_ID_COLUMN
    ):
        raise RegistrationSyncError(
            "Registration sheet has no valid final Registration ID column. "
            "Run a backed-up full sync before append mode."
        )
    if expected_header is not None and header != expected_header:
        raise RegistrationSyncError(
            "Registration sheet columns no longer match the event configuration. "
            "Run a backed-up full sync before append mode."
        )
    id_index = header.index(REGISTRATION_ID_COLUMN)
    return {row[id_index].strip() for row in values[1:] if len(row) > id_index and row[id_index].strip()}


def backup_legacy_sheet_if_needed(
    worksheet,
    values: list[list[str]],
    *,
    expected_header: list[str] | None = None,
) -> None:
    """Duplicate a populated worksheet before replacing a legacy/drifted schema."""
    if not values or len(values) <= 1:
        return
    current_header = values[0]
    needs_backup = REGISTRATION_ID_COLUMN not in current_header
    if expected_header is not None:
        needs_backup = needs_backup or current_header != expected_header
    if not needs_backup:
        return
    spreadsheet = getattr(worksheet, "spreadsheet", None) or getattr(worksheet, "_spreadsheet", None)
    worksheet_id = getattr(worksheet, "id", None)
    worksheet_title = getattr(worksheet, "title", "Registrations")
    duplicate = getattr(spreadsheet, "duplicate_sheet", None)
    if not callable(duplicate) or worksheet_id is None:
        raise RegistrationSyncError("Legacy registration sheet must be backed up before adding Registration ID.")
    duplicate(
        source_sheet_id=worksheet_id,
        new_sheet_name=(
            f"{worksheet_title} backup before Registration ID {datetime.now(UTC).strftime('%Y%m%d-%H%M%S-%f')}"
        )[:100],
    )


def ensure_registration_id_protected(
    worksheet,
    header: list[str],
    *,
    editor_email: str = "",
) -> None:
    """Protect the application-owned final ID column while retaining service access."""
    if not header or header[-1] != REGISTRATION_ID_COLUMN:
        raise RegistrationSyncError("Registration ID must be the final sheet column.")

    spreadsheet = getattr(worksheet, "spreadsheet", None) or getattr(worksheet, "_spreadsheet", None)
    worksheet_id = getattr(worksheet, "id", None)
    add_protected_range = getattr(worksheet, "add_protected_range", None)
    if spreadsheet is None or worksheet_id is None or not callable(add_protected_range):
        raise RegistrationSyncError("Registration ID column could not be protected.")

    id_column_index = len(header) - 1
    metadata = spreadsheet.fetch_sheet_metadata(params={"fields": "sheets(properties(sheetId),protectedRanges)"})
    matching_protection = False
    stale_protection_ids: list[int] = []
    if isinstance(metadata, dict):
        for sheet in metadata.get("sheets", []):
            if sheet.get("properties", {}).get("sheetId") != worksheet_id:
                continue
            for protected_range in sheet.get("protectedRanges", []):
                if protected_range.get("description") != _ID_PROTECTION_DESCRIPTION:
                    continue
                grid_range = protected_range.get("range", {})
                if (
                    grid_range.get("startColumnIndex") == id_column_index
                    and grid_range.get("endColumnIndex") == id_column_index + 1
                ):
                    matching_protection = True
                elif protected_range.get("protectedRangeId") is not None:
                    stale_protection_ids.append(protected_range["protectedRangeId"])

    for protected_range_id in stale_protection_ids:
        worksheet.delete_protected_range(protected_range_id)
    if matching_protection:
        return

    from gspread.utils import rowcol_to_a1

    column_name = rowcol_to_a1(1, id_column_index + 1).rstrip("1")
    add_protected_range(
        f"{column_name}:{column_name}",
        editor_users_emails=[editor_email] if editor_email else [],
        description=_ID_PROTECTION_DESCRIPTION,
        warning_only=False,
        requesting_user_can_edit=True,
    )


def service_account_email(credentials) -> str:
    info = credentials.get_credentials_info()
    if not isinstance(info, dict):
        return ""
    return str(info.get("client_email") or "")


def _get_worksheet_by_gid(spreadsheet, worksheet_gid: int):
    return next(
        (worksheet for worksheet in spreadsheet.worksheets() if worksheet.id == worksheet_gid),
        None,
    )


def _get_worksheet(event: Event):
    credentials = GoogleCredentialConfig.load()
    if not credentials.is_configured:
        raise RegistrationSyncError("No active Google service account is configured.")

    import gspread

    client = gspread.service_account_from_dict(credentials.get_credentials_info())
    spreadsheet = client.open_by_key(event.registration_sheet_id)

    if event.registration_sheet_gid is not None:
        worksheet = _get_worksheet_by_gid(spreadsheet, int(event.registration_sheet_gid))
        if worksheet is None:
            raise RegistrationSyncError("Registration worksheet GID not found in the spreadsheet.")
    else:
        worksheet = spreadsheet.sheet1

    return worksheet
