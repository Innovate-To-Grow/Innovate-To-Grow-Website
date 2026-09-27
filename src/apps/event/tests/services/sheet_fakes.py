"""In-memory Sheets surface; every test runs without Google credentials or requests."""

from copy import deepcopy


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


class FakeSpreadsheet:
    def __init__(self):
        self.sheets = {}
        self.batches = []
        self.backups = []
        self.before_write = None
        self.after_write = None
        self.metadata_counter = 0

    def fetch_sheet_metadata(self, **_kwargs):
        return {
            "sheets": [
                {
                    "properties": {
                        "sheetId": sheet.id,
                        "title": sheet.title,
                        "gridProperties": {"rowCount": sheet.row_count, "columnCount": sheet.col_count},
                    },
                    "developerMetadata": deepcopy(sheet.metadata),
                    "protectedRanges": deepcopy(sheet.protections),
                }
                for sheet in self.sheets.values()
            ]
        }

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
        for request in body["requests"]:
            if "appendDimension" in request:
                data = request["appendDimension"]
                sheet = self.sheets[data["sheetId"]]
                if data["dimension"] == "ROWS":
                    sheet.row_count += data["length"]
                else:
                    sheet.col_count += data["length"]
            elif "createDeveloperMetadata" in request:
                entry = deepcopy(request["createDeveloperMetadata"]["developerMetadata"])
                self.metadata_counter += 1
                entry["metadataId"] = self.metadata_counter
                self.sheets[entry["location"]["dimensionRange"]["sheetId"]].metadata.append(entry)
            elif "updateDeveloperMetadata" in request:
                data = request["updateDeveloperMetadata"]
                identity = data["dataFilters"][0]["developerMetadataLookup"]["metadataId"]
                for sheet in self.sheets.values():
                    for entry in sheet.metadata:
                        if entry["metadataId"] == identity:
                            entry.update(data["developerMetadata"])
            elif "updateCells" in request:
                data = request["updateCells"]
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
            elif "addProtectedRange" in request:
                data = deepcopy(request["addProtectedRange"]["protectedRange"])
                data["protectedRangeId"] = len(self.sheets[data["range"]["sheetId"]].protections) + 1
                self.sheets[data["range"]["sheetId"]].protections.append(data)
            elif "deleteProtectedRange" in request:
                identity = request["deleteProtectedRange"]["protectedRangeId"]
                for sheet in self.sheets.values():
                    sheet.protections = [entry for entry in sheet.protections if entry["protectedRangeId"] != identity]
            elif "updateDimensionProperties" in request:
                grid = request["updateDimensionProperties"]["range"]
                self.sheets[grid["sheetId"]].hidden.add(grid["startIndex"] + 1)
            else:
                raise AssertionError(f"Unexpected provider write: {request}")
        if self.after_write:
            self.after_write()
        return {"replies": [{} for _ in body["requests"]]}
