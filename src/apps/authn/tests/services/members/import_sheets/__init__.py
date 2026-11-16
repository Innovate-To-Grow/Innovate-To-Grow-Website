"""Build in-memory .xlsx sheets for the member import tests."""

from io import BytesIO

from openpyxl import Workbook

FULL_HEADERS = [
    "Primary Email",
    "First Name",
    "Last Name",
    "Primary Verified",
    "Primary Subscribed",
    "Secondary Email",
    "Secondary Verified",
    "Secondary Subscribed",
    "Phone Number",
    "Phone Subscribed",
    "Active",
    "Organization",
]
# FULL_HEADERS plus the Phone Verified column: Export to Excel still writes it, and the import ignores it.
PHONE_VERIFIED_HEADERS = [*FULL_HEADERS, "Phone Verified"]


def build_sheet(headers: list[str], rows: list[list]) -> BytesIO:
    """A workbook whose active sheet holds ``headers`` and then ``rows``."""
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(headers)
    for row in rows:
        worksheet.append(row)
    payload = BytesIO()
    workbook.save(payload)
    payload.seek(0)
    return payload


def full_row(primary: str, cells: dict | None = None, headers: list[str] = FULL_HEADERS) -> list:
    """One ``headers`` row: ``cells`` maps a header to its value; names default to Ada Lovelace, the rest to blank."""
    unknown = set(cells or {}) - set(headers)
    if unknown:
        raise ValueError(f"cells for headers the sheet does not have: {sorted(unknown)}")
    values = {"First Name": "Ada", "Last Name": "Lovelace", **(cells or {})}
    return [primary if header == "Primary Email" else values.get(header) for header in headers]
