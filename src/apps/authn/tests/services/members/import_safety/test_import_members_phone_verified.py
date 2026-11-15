"""The member import ignores the Phone Verified column.

A verified phone number is a sign-in factor, so only the member's own one-time code may produce one. An import saves
every number it adds unverified, whatever the sheet says, and never changes the status of a number already stored
(verified stays verified, unverified stays unverified). A sheet may still have the column (Export to Excel writes it):
it is accepted, ignored, and reported once for the file.
"""

from django.test import SimpleTestCase

from apps.authn.services.members.import_.parsing import (
    FLAG_COLUMNS,
    IGNORED_COLUMNS,
    PHONE_VERIFIED_IGNORED,
    column_notes,
    normalize_header,
    parse_row,
)
from apps.authn.services.members.import_.types import ImportResult

from ..import_sheets import PHONE_VERIFIED_HEADERS, build_sheet, full_row

# Every kind of cell a Phone Verified column may hold: text and booleans in both directions, garbage, and blank.
CELLS = ("TRUE", "FALSE", "yes", "No", "1", "0", True, False, 1, 0, "maybe", "N/A", "x", 2, "", None)


def _sheet(rows):
    return build_sheet(PHONE_VERIFIED_HEADERS, rows)


def _row(primary, cells):
    return full_row(primary, cells, PHONE_VERIFIED_HEADERS)


def _number(index: int) -> str:
    return f"20955501{index:02d}"


class PhoneVerifiedParsingTests(SimpleTestCase):
    def test_every_header_spelling_is_recognised_as_the_ignored_column(self):
        for header in ("Phone Verified", "phone verified", " PHONE_VERIFIED ", "Phone Number Verified"):
            with self.subTest(header=header):
                self.assertEqual(normalize_header(header), "phone_verified")
        self.assertIn("phone_verified", IGNORED_COLUMNS)

    def test_the_column_is_not_a_flag_column_any_more(self):
        self.assertNotIn("phone_verified", FLAG_COLUMNS)
        self.assertIn("phone_subscribed", FLAG_COLUMNS)

    def test_a_parsed_row_carries_no_phone_verified_value_and_no_note_for_any_cell(self):
        for cell in CELLS:
            with self.subTest(cell=cell):
                parsed = parse_row(2, {"primary_email": "a@example.com", "phone_verified": cell})

                self.assertNotIn("phone_verified", parsed)
                self.assertEqual(parsed["notes"], [])

    def test_column_notes_name_the_ignored_column_only_when_the_sheet_has_it(self):
        self.assertEqual(column_notes(["primary_email", "phone_number", "phone_verified"]), [PHONE_VERIFIED_IGNORED])
        self.assertEqual(column_notes(["primary_email", "phone_number", "phone_subscribed"]), [])
        self.assertEqual(column_notes([]), [])

    def test_the_note_tells_staff_what_happens_instead(self):
        self.assertIn("Phone Verified column ignored", PHONE_VERIFIED_IGNORED)
        self.assertIn("never verifies or un-verifies a phone number", PHONE_VERIFIED_IGNORED)
        self.assertIn("saved unverified", PHONE_VERIFIED_IGNORED)
        self.assertIn("one-time code", PHONE_VERIFIED_IGNORED)

    def test_a_file_note_has_no_row_and_no_member_and_stays_before_the_rows(self):
        result = ImportResult(success=True)
        result.note_row(3, "a row note")
        result.note_file(PHONE_VERIFIED_IGNORED)

        result.sort_by_row()

        self.assertEqual(result.warnings, [PHONE_VERIFIED_IGNORED, "Row 3: a row note"])
        self.assertIsNone(result.warnings[0].row)
        self.assertIsNone(result.warnings[0].member_id)
