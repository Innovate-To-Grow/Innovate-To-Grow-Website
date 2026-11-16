"""Which of the event's developer metadata entries a sync deletes, and which it leaves for the planner."""

from django.test import SimpleTestCase

from apps.event.services.registration_sheet_sync.plan.schema import RegistrationField
from apps.event.services.registration_sheet_sync.worksheet.metadata_cleanup import redundant_metadata
from apps.event.services.registration_sheet_sync.worksheet.snapshot import SheetSnapshot

OWN = "i2g.registration.v1:event"
LABEL = "i2g.registration-label.v1:event"
FIELDS = [
    RegistrationField("order", "Order"),
    RegistrationField("first_name", "Given", aliases=("First Name",), explicit_label=True),
]


def _entry(identity, key, value, *, dimension="COLUMNS", start=0, sheet_id=42):
    span = {"sheetId": sheet_id, "dimension": dimension, "startIndex": start, "endIndex": start + 1}
    return {"metadataId": identity, "metadataKey": key, "metadataValue": value, "location": {"dimensionRange": span}}


def _label(identity, key, label, start=1):
    return _entry(identity, LABEL, f'{{"key":"{key}","label":"{label}"}}', start=start)


def _removed(*metadata, header=("Order", "First Name", "Notes"), header_row=1):
    values = [[] for _ in range(header_row - 1)] + [list(header)]
    snapshot = SheetSnapshot(42, "Registrations", values, 100, 26, list(metadata), [])
    return redundant_metadata(snapshot, FIELDS, event_id="event", header_row=header_row)


class RedundantMetadataTests(SimpleTestCase):
    def test_a_clean_worksheet_loses_nothing(self):
        clean = [
            _entry(1, OWN, "order"),
            _entry(2, OWN, "first_name", start=1),
            _entry(3, OWN, "__header__", dimension="ROWS"),
        ]
        self.assertEqual(_removed(*clean, _label(4, "first_name", "Given")), [])

    def test_copies_keep_the_entry_with_the_lowest_id(self):
        removed = _removed(_entry(9, OWN, "order"), _entry(3, OWN, "order"), _entry(5, OWN, "order"))
        self.assertEqual(removed, [5, 9])

    def test_entries_of_fields_that_no_longer_exist_are_removed(self):
        removed = _removed(
            _entry(1, OWN, "question:gone", start=4),
            _entry(2, OWN, "question:gone", start=4),
            _label(3, "question:gone", "Q"),
        )
        self.assertEqual(sorted(removed), [1, 2, 3])

    def test_a_field_bound_at_several_columns_keeps_the_column_still_headed_by_it(self):
        removed = _removed(
            _entry(2, OWN, "first_name", start=2),  # renamed to "Notes" by an organizer
            _entry(4, OWN, "first_name", start=1),  # headed by the field's default label
            _entry(6, OWN, "first_name", start=1),
            _entry(8, OWN, "first_name", dimension="ROWS", start=1),
        )
        self.assertEqual(sorted(removed), [2, 6, 8])

    def test_a_field_bound_at_columns_none_or_several_of_which_show_it_keeps_one_entry_per_column(self):
        neither = _removed(
            _entry(1, OWN, "first_name", start=2),
            _entry(2, OWN, "first_name", start=2),
            _entry(3, OWN, "first_name", start=0),
        )
        self.assertEqual(neither, [2])
        both = _removed(
            _entry(1, OWN, "first_name"), _entry(2, OWN, "first_name", start=1), header=("Given", "First Name")
        )
        self.assertEqual(both, [])

    def test_header_markers_keep_the_configured_row(self):
        markers = [
            _entry(1, OWN, "__header__", dimension="ROWS"),
            _entry(2, OWN, "__header__", dimension="ROWS", start=2),
        ]
        self.assertEqual(
            _removed(*markers, _entry(3, OWN, "__header__", dimension="ROWS", start=2), header_row=3), [1, 3]
        )
        # Without a marker on the configured row, the planner reports the mismatch.
        self.assertEqual(_removed(*markers, _entry(4, OWN, "__header__", dimension="ROWS"), header_row=5), [4])

    def test_label_copies_keep_the_entry_with_the_configured_label(self):
        self.assertEqual(_removed(_label(1, "first_name", "Old"), _label(2, "first_name", "Given")), [1])
        self.assertEqual(_removed(_label(1, "first_name", "Old"), _label(2, "first_name", "Older")), [2])

    def test_entries_it_cannot_attribute_are_left_for_the_planner(self):
        kept = [
            {**_entry(1, OWN, "order"), "metadataId": None},
            _entry(2, OWN, "order", sheet_id=7),
            {"metadataId": 3, "metadataKey": OWN, "metadataValue": "order", "location": {"sheetId": 42}},
            _entry(4, OWN, ""),
            _entry(5, LABEL, "not json"),
            _entry(6, LABEL, '{"label": "no key"}'),
            _entry(7, LABEL, "[1, 2]"),
            _entry(8, "i2g.registration.v1:other-event", "order"),
            _entry(9, OWN, "order"),
        ]
        self.assertEqual(_removed(*kept), [])
