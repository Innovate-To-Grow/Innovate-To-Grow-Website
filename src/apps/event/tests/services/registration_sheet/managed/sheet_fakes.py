"""In-memory Sheets surface; every test runs without Google credentials or requests.

It answers the way Google does where the sync depends on it: a sheet's own ``developerMetadata`` lists sheet-level
entries only, while entries on rows and columns come back inside the grid data, and only when the field mask asks
for it; a batch applies all of its requests or none; a sheet holds at most 30,000 characters of developer metadata.
"""

import json
from copy import deepcopy

from gspread.exceptions import APIError
from requests import Response

METADATA_LIMIT = 30_000
STORAGE_LIMIT_MESSAGE = "Adding the requested developer metadata would exceed the allowed storage limit."


def metadata_size(entries):
    """The characters Google counts toward the limit: every key and value."""
    return sum(len(entry.get("metadataKey", "")) + len(entry.get("metadataValue", "")) for entry in entries)


def api_error(message, status=400):
    response = Response()
    response.status_code = status
    response._content = json.dumps(  # noqa: SLF001 - build the response gspread expects.
        {"error": {"code": status, "message": message, "status": "INVALID_ARGUMENT"}}
    ).encode()
    return APIError(response)


class FakeWorksheet:
    def __init__(self, values=None, *, sheet_id=42, title="Registrations", rows=100, cols=26, spreadsheet=None):
        self.id = sheet_id
        self.title = title
        self.row_count = rows
        self.col_count = cols
        self.values = deepcopy(values or [])
        self.metadata = []
        self.protections = []
        self.hidden = set()
        self.spreadsheet = spreadsheet or FakeSpreadsheet()
        self.spreadsheet.sheets[self.id] = self

    def get_all_values(self, **_kwargs):
        return deepcopy(self.values)

    def resource(self, grid_metadata):
        resource = {
            "properties": {
                "sheetId": self.id,
                "title": self.title,
                "gridProperties": {"rowCount": self.row_count, "columnCount": self.col_count},
            },
            "developerMetadata": deepcopy(
                [entry for entry in self.metadata if "dimensionRange" not in entry["location"]]
            ),
            "protectedRanges": deepcopy(self.protections),
        }
        if grid_metadata:
            resource["data"] = [
                {
                    "rowMetadata": self._dimension_metadata("ROWS", self.row_count),
                    "columnMetadata": self._dimension_metadata("COLUMNS", self.col_count),
                }
            ]
        return resource

    def _dimension_metadata(self, dimension, count):
        spans = [
            entry
            for entry in self.metadata
            if entry["location"].get("dimensionRange", {}).get("dimension") == dimension
        ]
        found = [[] for _ in range(max([count, *(entry["location"]["dimensionRange"]["endIndex"] for entry in spans)]))]
        for entry in spans:
            found[entry["location"]["dimensionRange"]["startIndex"]].append(deepcopy(entry))
        return [{"developerMetadata": entries} if entries else {} for entries in found]


class FakeSpreadsheet:
    def __init__(self):
        self.sheets = {}
        self.batches = []
        self.backups = []
        self.before_write = None
        self.after_write = None
        self.metadata_counter = 0

    def fetch_sheet_metadata(self, params=None):
        grid_metadata = "columnMetadata" in (params or {}).get("fields", "")
        return {"sheets": [sheet.resource(grid_metadata) for sheet in self.sheets.values()]}

    def duplicate_sheet(self, source_sheet_id, new_sheet_name):
        source = self.sheets[source_sheet_id]
        copied = FakeWorksheet(
            source.values,
            sheet_id=max(self.sheets) + 1,
            title=new_sheet_name,
            rows=source.row_count,
            cols=source.col_count,
            spreadsheet=self,
        )
        self.backups.append(copied)
        return copied

    def add_worksheet(self, title, rows, cols):
        return FakeWorksheet(sheet_id=max(self.sheets) + 1, title=title, rows=rows, cols=cols, spreadsheet=self)

    def batch_update(self, body):
        if self.before_write:
            self.before_write()
        self.batches.append(deepcopy(body))
        saved = {
            sheet: deepcopy({k: v for k, v in vars(sheet).items() if k != "spreadsheet"})
            for sheet in self.sheets.values()
        }
        try:
            for index, request in enumerate(body["requests"]):
                ((name, data),) = request.items()
                handler = getattr(self, f"_{name}", None)
                if handler is None:
                    raise AssertionError(f"Unexpected provider write: {request}")
                handler(data, index)
        except Exception:
            # Google applies a batch atomically: a rejected request leaves the spreadsheet as it was.
            for sheet, state in saved.items():
                vars(sheet).update(state)
            raise
        if self.after_write:
            self.after_write()
        return {"replies": [{} for _ in body["requests"]]}

    def _appendDimension(self, data, _index):
        sheet = self.sheets[data["sheetId"]]
        if data["dimension"] == "ROWS":
            sheet.row_count += data["length"]
        else:
            sheet.col_count += data["length"]

    def _createDeveloperMetadata(self, data, index):
        entry = deepcopy(data["developerMetadata"])
        self.metadata_counter += 1
        entry["metadataId"] = self.metadata_counter
        sheet = self.sheets[entry["location"]["dimensionRange"]["sheetId"]]
        if metadata_size([*sheet.metadata, entry]) > METADATA_LIMIT:
            raise api_error(f"Invalid requests[{index}].createDeveloperMetadata: {STORAGE_LIMIT_MESSAGE}")
        sheet.metadata.append(entry)

    def _updateDeveloperMetadata(self, data, _index):
        identity = data["dataFilters"][0]["developerMetadataLookup"]["metadataId"]
        for sheet in self.sheets.values():
            for entry in sheet.metadata:
                if entry["metadataId"] == identity:
                    entry.update(data["developerMetadata"])

    def _deleteDeveloperMetadata(self, data, _index):
        identity = data["dataFilter"]["developerMetadataLookup"]["metadataId"]
        for sheet in self.sheets.values():
            sheet.metadata = [entry for entry in sheet.metadata if entry["metadataId"] != identity]

    def _updateCells(self, data, _index):
        grid = data["range"]
        sheet = self.sheets[grid["sheetId"]]
        for offset, row in enumerate(data["rows"]):
            row_index = grid["startRowIndex"] + offset
            while len(sheet.values) <= row_index:
                sheet.values.append([])
            for col_offset, cell in enumerate(row["values"]):
                column = grid["startColumnIndex"] + col_offset
                while len(sheet.values[row_index]) <= column:
                    sheet.values[row_index].append("")
                sheet.values[row_index][column] = cell["userEnteredValue"]["stringValue"]

    def _addProtectedRange(self, data, _index):
        protected = deepcopy(data["protectedRange"])
        protected["protectedRangeId"] = len(self.sheets[protected["range"]["sheetId"]].protections) + 1
        self.sheets[protected["range"]["sheetId"]].protections.append(protected)

    def _deleteProtectedRange(self, data, _index):
        for sheet in self.sheets.values():
            sheet.protections = [
                entry for entry in sheet.protections if entry["protectedRangeId"] != data["protectedRangeId"]
            ]

    def _updateDimensionProperties(self, data, _index):
        grid = data["range"]
        self.sheets[grid["sheetId"]].hidden.add(grid["startIndex"] + 1)
