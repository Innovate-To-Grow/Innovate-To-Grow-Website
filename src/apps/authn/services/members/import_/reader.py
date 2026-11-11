"""Open an uploaded member sheet: pick the worksheet, map its headers, and parse its data rows.

Only the parsed values are kept, never the file. The worksheet read is the active one when it has a Primary Email
column, otherwise the first one that has; a workbook saved with its Instructions tab open used to import nothing.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from io import BytesIO

try:
    from openpyxl import load_workbook
except ImportError:  # pragma: no cover - openpyxl is a hard dependency; guarded for the import error message
    load_workbook = None

from .parsing import FLAG_COLUMNS, IMPORTED_KEYS, INFORMATIONAL_KEYS, normalize_header, parse_row

EMPTY_FILE = "Excel file is empty"
NO_PRIMARY_EMAIL_COLUMN = "Excel file must contain a 'Primary Email' column"
UNREADABLE = "The file could not be read as an .xlsx workbook"
NO_OPENPYXL = "openpyxl library not installed. Please run: pip install openpyxl"
# How a recognised column is named on the review page.
COLUMN_LABELS = {
    "member_uuid": "Member UUID",
    "first_name": "First Name",
    "last_name": "Last Name",
    "middle_name": "Middle Name",
    "title": "Title",
    "organization": "Organization",
    "when_started": "When Started",
    "primary_email": "Primary Email",
    "secondary_email": "Secondary Email",
    "phone_number": "Phone Number",
    "last_updated": "Last Updated",
    "primary_expired": "Primary Expired",
    "secondary_expired": "Secondary Expired",
    "secondary_bounced": "Secondary Bounced",
    **FLAG_COLUMNS,
}


@dataclass
class SheetRead:
    """What an upload holds: the file's identity, the worksheet read, its columns and its parsed rows."""

    file_name: str = ""
    file_size: int = 0
    file_sha256: str = ""
    sheet_name: str = ""
    columns: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)
    error: str = ""


def read_upload(file, *, max_rows: int | None = None, max_rows_read: int | None = None) -> SheetRead:
    """Read ``file`` (an upload or any binary file object). ``error`` is set when nothing can be imported.

    ``max_rows`` caps the member rows (blank rows don't count); ``max_rows_read`` caps every row read, blank ones
    included. Both stop the reading as soon as they are passed, so a small, highly compressed workbook can't expand
    into millions of rows in a web worker.
    """
    data = file.read()
    read = SheetRead(
        file_name=str(getattr(file, "name", "") or "upload.xlsx")[:255],
        file_size=len(data),
        file_sha256=hashlib.sha256(data).hexdigest(),
    )
    if load_workbook is None:
        read.error = NO_OPENPYXL
        return read
    try:
        workbook = load_workbook(filename=BytesIO(data), read_only=True, data_only=True)
    except Exception:  # noqa: BLE001 - any parse failure means the same thing to the admin.
        read.error = UNREADABLE
        return read
    try:
        _read_workbook(workbook, read, max_rows, max_rows_read)
    finally:
        workbook.close()
    return read


def _read_workbook(workbook, read: SheetRead, max_rows: int | None, max_rows_read: int | None) -> None:
    sheets = list(workbook.worksheets)
    header_rows = [next(sheet.iter_rows(values_only=True), None) for sheet in sheets]
    if all(header is None for header in header_rows):
        read.error = EMPTY_FILE
        return
    active = sheets.index(workbook.active) if workbook.active in sheets else 0
    order = [active, *(index for index in range(len(sheets)) if index != active)]
    chosen = next((index for index in order if header_rows[index] and _has_primary_email(header_rows[index])), None)
    if chosen is None:
        read.error = NO_PRIMARY_EMAIL_COLUMN
        return
    read.sheet_name = sheets[chosen].title
    read.warnings.extend(_sheet_warnings(sheets, chosen, active))
    rows = sheets[chosen].iter_rows(values_only=True)
    raw_headers = next(rows)
    headers = [normalize_header(header) for header in raw_headers]
    read.columns = _describe_columns(raw_headers, headers)
    read.warnings.extend(_duplicate_column_warnings(raw_headers, headers))
    data_rows = _data_rows(rows, read, max_rows, max_rows_read)
    if not read.error:
        read.rows = [parse_row(number, dict(zip(headers, row, strict=False))) for number, row in data_rows]


def _data_rows(rows, read: SheetRead, max_rows: int | None, max_rows_read: int | None) -> list:
    """The non-blank rows with their sheet row numbers; stops (setting ``read.error``) as soon as a cap is passed."""
    data_rows = []
    for number, row in enumerate(rows, start=2):
        if max_rows_read is not None and number - 1 > max_rows_read:
            read.error = (
                f"The sheet has more than {max_rows_read} rows, counting blank ones. Copy the member rows into a new "
                "workbook and upload that."
            )
            return []
        if not any(_filled(row)):
            continue
        data_rows.append((number, row))
        if max_rows is not None and len(data_rows) > max_rows:
            read.error = (
                f"The sheet has more than {max_rows} member rows; one import takes at most {max_rows}. Split the file "
                "and import the parts one after another."
            )
            return []
    return data_rows


def _filled(row):
    return (cell is not None and str(cell).strip() != "" for cell in row)


def _has_primary_email(header_row) -> bool:
    return "primary_email" in {normalize_header(header) for header in header_row}


def _sheet_warnings(sheets, chosen: int, active: int) -> list[str]:
    warnings = []
    name = sheets[chosen].title
    if chosen != active:
        warnings.append(
            f'The workbook was saved with the "{sheets[active].title}" sheet open, which has no Primary Email '
            f'column; the "{name}" sheet was read instead.'
        )
    elif chosen != 0:
        warnings.append(f'The "{name}" sheet was read; it is not the first sheet of the workbook.')
    if name.strip().lower() == "instructions":
        warnings.append('The sheet read is called "Instructions". Check that it holds the members.')
    return warnings


def _describe_columns(raw_headers, headers: list[str]) -> dict:
    recognised, informational, ignored = [], [], []
    for raw, key in zip(raw_headers, headers, strict=False):
        label = str(raw).strip() if raw is not None else ""
        if not label:
            continue
        if key in IMPORTED_KEYS:
            recognised.append(label)
        elif key in INFORMATIONAL_KEYS:
            informational.append(label)
        else:
            ignored.append(label)
    keys = [key for key in dict.fromkeys(headers) if key in IMPORTED_KEYS]
    return {
        "recognised": recognised,
        "informational": informational,
        "ignored": ignored,
        "keys": keys,
        "has_member_uuid": "member_uuid" in keys,
    }


def _duplicate_column_warnings(raw_headers, headers: list[str]) -> list[str]:
    seen: dict[str, str] = {}
    warnings = []
    for raw, key in zip(raw_headers, headers, strict=False):
        if key not in IMPORTED_KEYS:
            continue
        label = str(raw).strip()
        if key in seen:
            warnings.append(
                f'Columns "{seen[key]}" and "{label}" both mean {COLUMN_LABELS.get(key, key)}; only the last one '
                "is read."
            )
        seen[key] = label
    return warnings
