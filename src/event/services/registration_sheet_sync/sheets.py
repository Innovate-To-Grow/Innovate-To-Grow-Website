from core.models import GoogleCredentialConfig
from event.models import Event


class RegistrationSyncError(RuntimeError):
    """Raised when registration sheet sync fails."""


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
