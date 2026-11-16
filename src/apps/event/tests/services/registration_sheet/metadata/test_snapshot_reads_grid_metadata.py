"""The snapshot reads the developer metadata Google keeps on rows and columns, not only sheet-level entries."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from django.test import SimpleTestCase

from apps.event.services.registration_sheet_sync.worksheet.snapshot import read_snapshot

KEY = "i2g.registration.v1:event"


def _worksheet(response, *, sheet_id):
    spreadsheet = MagicMock()
    spreadsheet.fetch_sheet_metadata.return_value = response
    return SimpleNamespace(
        id=sheet_id,
        title="Registrations",
        row_count=100,
        col_count=26,
        spreadsheet=spreadsheet,
        get_all_values=lambda **_kwargs: [["Order", "Registration ID"]],
    )


def _sheet(sheet_id, **extra):
    properties = {"sheetId": sheet_id, "title": f"Sheet {sheet_id}", "gridProperties": {"rowCount": 100}}
    return {"properties": properties, **extra}


class SnapshotGridMetadataTests(SimpleTestCase):
    def test_entries_on_rows_and_columns_are_read_from_the_grid_data(self):
        # Sheet 0, row 1 and column A are zero values, which Google may leave out of a location.
        marker = {"metadataId": 1, "metadataKey": KEY, "metadataValue": "__header__"}
        order = {
            "metadataId": 2,
            "metadataKey": KEY,
            "metadataValue": "order",
            "location": {"locationType": "COLUMN", "dimensionRange": {"dimension": "COLUMNS", "endIndex": 1}},
        }
        identity = {
            "metadataId": 3,
            "metadataKey": KEY,
            "metadataValue": "registration_id",
            "location": {
                "locationType": "COLUMN",
                "dimensionRange": {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 2},
            },
        }
        backup = {**identity, "metadataId": 4}
        response = {
            "sheets": [
                _sheet(
                    0,
                    data=[
                        {
                            "rowMetadata": [{"developerMetadata": [marker]}, {}],
                            "columnMetadata": [{"developerMetadata": [order]}, {"developerMetadata": [identity]}],
                        }
                    ],
                ),
                _sheet(7, data=[{"columnMetadata": [{}, {"developerMetadata": [backup]}]}]),
            ]
        }
        worksheet = _worksheet(response, sheet_id=0)

        snapshot = read_snapshot(worksheet)

        self.assertEqual([entry["metadataId"] for entry in snapshot.metadata], [1, 2, 3])
        located = {entry["metadataId"]: entry["location"]["dimensionRange"] for entry in snapshot.metadata}
        self.assertEqual(located[1], {"sheetId": 0, "dimension": "ROWS", "startIndex": 0, "endIndex": 1})
        self.assertEqual(located[2], {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1})
        self.assertEqual(located[3], {"sheetId": 0, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 2})
        fields = worksheet.spreadsheet.fetch_sheet_metadata.call_args.kwargs["params"]["fields"]
        self.assertIn("rowMetadata(developerMetadata)", fields)
        self.assertIn("columnMetadata(developerMetadata)", fields)

    def test_grid_offsets_place_entries_on_their_own_row_or_column(self):
        entry = {"metadataId": 5, "metadataKey": KEY, "metadataValue": "status"}
        response = {
            "sheets": [_sheet(9, data=[{"startColumn": 3, "columnMetadata": [{}, {"developerMetadata": [entry]}]}])]
        }

        snapshot = read_snapshot(_worksheet(response, sheet_id=9))

        span = snapshot.metadata[0]["location"]["dimensionRange"]
        self.assertEqual((span["sheetId"], span["dimension"], span["startIndex"]), (9, "COLUMNS", 4))

    def test_sheet_level_entries_are_still_read(self):
        entry = {"metadataId": 6, "metadataKey": "com.example.other", "location": {"sheetId": 9}}
        response = {"sheets": [_sheet(9, developerMetadata=[entry])]}

        self.assertEqual(read_snapshot(_worksheet(response, sheet_id=9)).metadata, [entry])
