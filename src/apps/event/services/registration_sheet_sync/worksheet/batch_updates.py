"""Atomic, text-only managed-cell writes: the batchUpdate requests a plan becomes, and applying them."""

import json

from gspread.exceptions import APIError

from .sheets import RegistrationSyncConflict, RegistrationSyncError
from .snapshot import HEADER_MARKER, LABEL_METADATA_PREFIX, METADATA_PREFIX, read_snapshot, spreadsheet_for

METADATA_STORAGE_FULL = (
    "Google Sheets refused the sync: this worksheet has reached Google's limit of 30,000 characters of developer "
    "metadata per sheet. Open Manage sync and use Review new worksheet to move the export to a new worksheet."
)


def _metadata_request(snapshot, key, value, dimension, start):
    """Create developer metadata on one row or column (0-based ``start``)."""
    return {
        "createDeveloperMetadata": {
            "developerMetadata": {
                "metadataKey": key,
                "metadataValue": value,
                "visibility": "DOCUMENT",
                "location": {
                    "dimensionRange": {
                        "sheetId": snapshot.sheet_id,
                        "dimension": dimension,
                        "startIndex": start,
                        "endIndex": start + 1,
                    }
                },
            }
        }
    }


def _grid_growth_requests(plan, snapshot):
    highest_row = max([snapshot.row_count, *[row for row, _ in plan.cells]])
    highest_column = max([snapshot.column_count, *plan.bindings.values()])
    return [
        {"appendDimension": {"sheetId": snapshot.sheet_id, "dimension": dimension, "length": target - current}}
        for dimension, current, target in (
            ("ROWS", snapshot.row_count, highest_row),
            ("COLUMNS", snapshot.column_count, highest_column),
        )
        if target > current
    ]


def _label_requests(plan, snapshot, event_id):
    requests = []
    for label in plan.label_changes:
        value = json.dumps({"key": label["key"], "label": label["label"]}, separators=(",", ":"))
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
                _metadata_request(snapshot, f"{LABEL_METADATA_PREFIX}{event_id}", value, "COLUMNS", label["column"] - 1)
            )
    return requests


def _cell_update_requests(plan, snapshot):
    # Separate managed columns ensure custom cells/formulas/styles are never part of the write mask.
    cells = plan.cells
    requests = []
    for column in sorted({column for _, column in cells}):
        groups = []
        for row in sorted(row for row, col in cells if col == column):
            if not groups or row != groups[-1][-1] + 1:
                groups.append([])
            groups[-1].append(row)
        requests.extend(
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
            for group in groups
        )
    return requests


def _id_protection_requests(snapshot, id_column, event_id, editor_email):
    """Keep exactly one non-warning protection on the Registration ID column, editable only by ``editor_email``."""
    id_range = {"sheetId": snapshot.sheet_id, "startColumnIndex": id_column - 1, "endColumnIndex": id_column}
    description = f"Innovate to Grow Registration ID {event_id}"
    own = [
        item
        for item in snapshot.protections
        if item.get("description") in {description, "Innovate to Grow application-managed Registration ID"}
    ]
    desired_editors = {"users": [editor_email]} if editor_email else {}
    if len(own) == 1 and any(
        item.get("range") == id_range
        and not item.get("warningOnly", False)
        and item.get("editors", {}) == desired_editors
        for item in own
    ):
        return []
    return [
        *({"deleteProtectedRange": {"protectedRangeId": item["protectedRangeId"]}} for item in own),
        {
            "addProtectedRange": {
                "protectedRange": {
                    "range": id_range,
                    "description": description,
                    "warningOnly": False,
                    "editors": desired_editors,
                }
            }
        },
    ]


def build_requests(plan, snapshot, *, event_id, header_row=1, editor_email=""):
    """The batchUpdate that applies ``plan``: redundant metadata out, grid growth, ownership metadata, cell values,
    ID protection."""
    own_key = f"{METADATA_PREFIX}{event_id}"
    removed = set(plan.removed_metadata)
    # Deletions come first: Google checks its per-sheet metadata storage limit request by request.
    requests = [
        {"deleteDeveloperMetadata": {"dataFilter": {"developerMetadataLookup": {"metadataId": identity}}}}
        for identity in plan.removed_metadata
    ]
    requests.extend(_grid_growth_requests(plan, snapshot))
    requests.extend(
        _metadata_request(snapshot, own_key, key, "COLUMNS", column - 1) for key, column in plan.new_bindings.items()
    )
    requests.extend(_label_requests(plan, snapshot, event_id))
    if not any(
        entry.get("metadataKey") == own_key
        and entry.get("metadataValue") == HEADER_MARKER
        and entry.get("metadataId") not in removed
        for entry in snapshot.metadata
    ):
        requests.append(_metadata_request(snapshot, own_key, HEADER_MARKER, "ROWS", header_row - 1))
    requests.extend(_cell_update_requests(plan, snapshot))
    id_column = plan.bindings["registration_id"]
    requests.extend(_id_protection_requests(snapshot, id_column, event_id, editor_email))
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
    try:
        spreadsheet_for(worksheet).batch_update({"requests": requests})
    except APIError as exc:
        message = str(exc).lower()
        if "developer metadata" in message and "storage limit" in message:
            raise RegistrationSyncError(METADATA_STORAGE_FULL) from exc
        raise
