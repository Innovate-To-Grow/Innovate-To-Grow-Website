"""Reading a worksheet: the destination lock, the snapshot every plan is computed from (its cells and developer
metadata), and the backup copy."""

import hashlib
import json
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime

from django.db import connection

from .sheets import RegistrationSyncError

METADATA_PREFIX = "i2g.registration.v1:"
LABEL_METADATA_PREFIX = "i2g.registration-label.v1:"
HEADER_MARKER = "__header__"
# A sheet's own ``developerMetadata`` lists sheet-level entries only. Google returns the entries on rows and columns
# (every column binding and the header-row marker) inside the grid data, one list per row or column.
_METADATA_FIELDS = (
    "developerMetadata,sheets(properties,developerMetadata,protectedRanges,"
    "data(startRow,startColumn,rowMetadata(developerMetadata),columnMetadata(developerMetadata)))"
)


def lock_destination(spreadsheet_id, worksheet_id):
    """Serialize independent events sharing a destination before reading identity.

    Production PostgreSQL holds this lock through the surrounding transaction.
    SQLite is used only by single-writer local tests, not provider workers.
    """
    if connection.vendor == "postgresql":
        identity = json.dumps([str(spreadsheet_id).strip(), int(worksheet_id)], separators=(",", ":"))
        key = int.from_bytes(hashlib.sha256(identity.encode()).digest()[:8], byteorder="big", signed=True)
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [key])


@dataclass
class SheetSnapshot:
    sheet_id: int
    title: str
    values: list[list[str]]
    row_count: int
    column_count: int
    metadata: list[dict]
    protections: list[dict]

    def fingerprint(self):
        return hashlib.sha256(json.dumps(self.__dict__, sort_keys=True, default=str).encode()).hexdigest()


def normalized_label(value):
    return " ".join(unicodedata.normalize("NFC", str(value)).split()).casefold()


def _cell(snapshot, row, column):
    return (
        str(snapshot.values[row - 1][column - 1])
        if row <= len(snapshot.values) and column <= len(snapshot.values[row - 1])
        else ""
    )


def spreadsheet_for(worksheet):
    return getattr(worksheet, "spreadsheet", None) or worksheet._spreadsheet


def _located(entry, sheet_id, dimension, index):
    """Fill in a row or column entry's location from where Google listed it; Google may omit zero values."""
    span = entry.setdefault("location", {}).setdefault("dimensionRange", {})
    for name, value in (
        ("sheetId", sheet_id),
        ("dimension", dimension),
        ("startIndex", index),
        ("endIndex", index + 1),
    ):
        span.setdefault(name, value)
    return entry


def _dimension_metadata(sheet, sheet_id):
    """The developer metadata on the sheet's rows and columns."""
    for grid in sheet.get("data", []):
        for field, dimension, start in (
            ("rowMetadata", "ROWS", grid.get("startRow", 0)),
            ("columnMetadata", "COLUMNS", grid.get("startColumn", 0)),
        ):
            for index, properties in enumerate(grid.get(field, []), start=start):
                yield from (
                    _located(entry, sheet_id, dimension, index) for entry in properties.get("developerMetadata", [])
                )


def read_snapshot(worksheet):
    values = worksheet.get_all_values(value_render_option="FORMULA", pad_values=False)
    if not isinstance(values, list) or any(not isinstance(row, list) for row in values):
        raise RegistrationSyncError("Unable to read worksheet values safely.")
    metadata = spreadsheet_for(worksheet).fetch_sheet_metadata(params={"fields": _METADATA_FIELDS})
    if not isinstance(metadata, dict):
        raise RegistrationSyncError("Unable to read worksheet metadata safely.")
    sheet_id = worksheet.id
    sheet = next(
        (item for item in metadata.get("sheets", []) if item.get("properties", {}).get("sheetId") == sheet_id), None
    )
    if sheet is None:
        raise RegistrationSyncError("The configured worksheet no longer exists.")
    properties = sheet["properties"]
    grid = properties.get("gridProperties", {})
    # The same metadata may be returned at spreadsheet and sheet level.
    entries = {
        entry.get("metadataId", json.dumps(entry, sort_keys=True)): entry
        for entry in [
            *metadata.get("developerMetadata", []),
            *sheet.get("developerMetadata", []),
            *_dimension_metadata(sheet, sheet_id),
        ]
    }
    return SheetSnapshot(
        sheet_id=sheet_id,
        title=properties.get("title", worksheet.title),
        values=values,
        row_count=int(grid.get("rowCount", worksheet.row_count)),
        column_count=int(grid.get("columnCount", worksheet.col_count)),
        metadata=[
            entry
            for entry in entries.values()
            if entry.get("location", {})
            .get("dimensionRange", {})
            .get("sheetId", entry.get("location", {}).get("sheetId"))
            == sheet_id
        ],
        protections=sheet.get("protectedRanges", []),
    )


def backup_worksheet(worksheet):
    title = f"{worksheet.title[:55]} backup {datetime.now(UTC).strftime('%Y%m%d-%H%M%S-%f')}"
    return spreadsheet_for(worksheet).duplicate_sheet(source_sheet_id=worksheet.id, new_sheet_name=title)
