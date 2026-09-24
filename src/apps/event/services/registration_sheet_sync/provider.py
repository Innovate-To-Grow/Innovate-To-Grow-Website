"""Narrow Google Sheets reads and atomic, text-only managed-cell writes."""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime

from django.db import connection

from .sheets import RegistrationSyncConflict, RegistrationSyncError

METADATA_PREFIX = "i2g.registration.v1:"


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


def spreadsheet_for(worksheet):
    return getattr(worksheet, "spreadsheet", None) or worksheet._spreadsheet


def read_snapshot(worksheet):
    values = worksheet.get_all_values(value_render_option="FORMULA", pad_values=False)
    if not isinstance(values, list) or any(not isinstance(row, list) for row in values):
        raise RegistrationSyncError("Unable to read worksheet values safely.")
    metadata = spreadsheet_for(worksheet).fetch_sheet_metadata(
        params={"fields": "developerMetadata,sheets(properties,developerMetadata,protectedRanges)"}
    )
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
        for entry in [*metadata.get("developerMetadata", []), *sheet.get("developerMetadata", [])]
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


def build_requests(plan, snapshot, *, event_id, header_row=1, editor_email=""):
    requests = []
    cells = plan.cells
    highest_row = max([snapshot.row_count, *[row for row, _ in cells]])
    highest_column = max([snapshot.column_count, *plan.bindings.values()])
    for dimension, current, target in (
        ("ROWS", snapshot.row_count, highest_row),
        ("COLUMNS", snapshot.column_count, highest_column),
    ):
        if target > current:
            requests.append(
                {"appendDimension": {"sheetId": snapshot.sheet_id, "dimension": dimension, "length": target - current}}
            )
    for key, column in plan.new_bindings.items():
        requests.append(
            {
                "createDeveloperMetadata": {
                    "developerMetadata": {
                        "metadataKey": f"{METADATA_PREFIX}{event_id}",
                        "metadataValue": key,
                        "visibility": "DOCUMENT",
                        "location": {
                            "dimensionRange": {
                                "sheetId": snapshot.sheet_id,
                                "dimension": "COLUMNS",
                                "startIndex": column - 1,
                                "endIndex": column,
                            }
                        },
                    }
                }
            }
        )
    for label in plan.label_changes:
        value = json.dumps({"key": label["key"], "label": label["label"]})
        if label["metadata_id"] is not None:
            requests.append(
                {
                    "updateDeveloperMetadata": {
                        "dataFilters": [{"developerMetadataLookup": {"metadataId": label["metadata_id"]}}],
                        "developerMetadata": {"metadataValue": value},
                        "fields": "metadataValue",
                    }
                }
            )
        else:
            requests.append(
                {
                    "createDeveloperMetadata": {
                        "developerMetadata": {
                            "metadataKey": f"i2g.registration-label.v1:{event_id}",
                            "metadataValue": value,
                            "visibility": "DOCUMENT",
                            "location": {
                                "dimensionRange": {
                                    "sheetId": snapshot.sheet_id,
                                    "dimension": "COLUMNS",
                                    "startIndex": label["column"] - 1,
                                    "endIndex": label["column"],
                                }
                            },
                        }
                    }
                }
            )
    if not any(
        entry.get("metadataKey") == f"{METADATA_PREFIX}{event_id}" and entry.get("metadataValue") == "__header__"
        for entry in snapshot.metadata
    ):
        requests.append(
            {
                "createDeveloperMetadata": {
                    "developerMetadata": {
                        "metadataKey": f"{METADATA_PREFIX}{event_id}",
                        "metadataValue": "__header__",
                        "visibility": "DOCUMENT",
                        "location": {
                            "dimensionRange": {
                                "sheetId": snapshot.sheet_id,
                                "dimension": "ROWS",
                                "startIndex": header_row - 1,
                                "endIndex": header_row,
                            }
                        },
                    }
                }
            }
        )
    # Separate managed columns ensure custom cells/formulas/styles are never part of the write mask.
    for column in sorted({column for _, column in cells}):
        rows = sorted(row for row, col in cells if col == column)
        groups = []
        for row in rows:
            if not groups or row != groups[-1][-1] + 1:
                groups.append([])
            groups[-1].append(row)
        for group in groups:
            requests.append(
                {
                    "updateCells": {
                        "range": {
                            "sheetId": snapshot.sheet_id,
                            "startRowIndex": group[0] - 1,
                            "endRowIndex": group[-1],
                            "startColumnIndex": column - 1,
                            "endColumnIndex": column,
                        },
                        "rows": [
                            {"values": [{"userEnteredValue": {"stringValue": cells[(row, column)]}}]} for row in group
                        ],
                        "fields": "userEnteredValue",
                    }
                }
            )
    id_column = plan.bindings["registration_id"]
    id_range = {"sheetId": snapshot.sheet_id, "startColumnIndex": id_column - 1, "endColumnIndex": id_column}
    description = f"Innovate to Grow Registration ID {event_id}"
    own = [
        item
        for item in snapshot.protections
        if item.get("description") in {description, "Innovate to Grow application-managed Registration ID"}
    ]
    desired_editors = {"users": [editor_email]} if editor_email else {}
    if len(own) != 1 or not any(
        item.get("range") == id_range
        and not item.get("warningOnly", False)
        and item.get("editors", {}) == desired_editors
        for item in own
    ):
        for item in own:
            requests.append({"deleteProtectedRange": {"protectedRangeId": item["protectedRangeId"]}})
        requests.append(
            {
                "addProtectedRange": {
                    "protectedRange": {
                        "range": id_range,
                        "description": description,
                        "warningOnly": False,
                        "editors": desired_editors,
                    }
                }
            }
        )
    requests.append(
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": snapshot.sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": id_column - 1,
                    "endIndex": id_column,
                },
                "properties": {"hiddenByUser": True},
                "fields": "hiddenByUser",
            }
        }
    )
    return requests


def apply_plan(worksheet, snapshot, plan, *, event_id, header_row=1, editor_email=""):
    if read_snapshot(worksheet).fingerprint() != snapshot.fingerprint():
        raise RegistrationSyncConflict("The worksheet changed while preparing the sync. Preview again before retrying.")
    requests = build_requests(plan, snapshot, event_id=event_id, header_row=header_row, editor_email=editor_email)
    # Metadata, all value updates, sizing and ID protection commit together at Google.
    spreadsheet_for(worksheet).batch_update({"requests": requests})
