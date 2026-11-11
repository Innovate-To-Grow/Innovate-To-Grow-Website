"""Reading an upload: which worksheet is read, its columns, the row cap, and what ``parse_row`` adds to each row."""

import hashlib
import uuid
from datetime import date, datetime
from io import BytesIO
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.authn.services.members.import_.parsing import cell_text, parse_flag, parse_row
from apps.authn.services.members.import_.reader import (
    EMPTY_FILE,
    NO_OPENPYXL,
    NO_PRIMARY_EMAIL_COLUMN,
    UNREADABLE,
    read_upload,
)
from apps.authn.tests.services.members.import_.helpers import (
    HEADERS,
    ImportTestCase,
    read,
    row,
    upload,
    workbook_bytes,
)

INSTRUCTIONS = ("Instructions", [["How to fill in this sheet"]])


def read_workbook(rows, **kwargs):
    return read_upload(BytesIO(workbook_bytes(HEADERS, rows, **kwargs)))


class SheetChoiceTests(ImportTestCase):
    def test_the_active_first_sheet_is_read_without_warnings(self):
        sheet = read(HEADERS, [row("ada@example.com")])

        self.assertEqual((sheet.error, sheet.sheet_name, sheet.warnings), ("", "Members", []))
        self.assertEqual([parsed["row"] for parsed in sheet.rows], [2])
        self.assertEqual(sheet.rows[0]["primary_email"], "ada@example.com")

    def test_an_active_sheet_without_primary_email_falls_back_to_the_members_sheet(self):
        sheet = read_workbook([row("ada@example.com")], sheets=[INSTRUCTIONS], active=0)

        self.assertEqual(sheet.sheet_name, "Members")
        self.assertEqual(
            sheet.warnings,
            [
                'The workbook was saved with the "Instructions" sheet open, which has no Primary Email column; the '
                '"Members" sheet was read instead.'
            ],
        )
        self.assertEqual([parsed["primary_email"] for parsed in sheet.rows], ["ada@example.com"])

    def test_the_first_sheet_with_a_primary_email_column_wins_the_fallback(self):
        older = ("Old export", [HEADERS, row("old@example.com")])

        sheet = read_workbook([row("ada@example.com")], sheets=[INSTRUCTIONS, older], active=0)

        self.assertEqual(sheet.sheet_name, "Old export")
        self.assertEqual([parsed["primary_email"] for parsed in sheet.rows], ["old@example.com"])

    def test_an_active_sheet_that_is_not_the_first_one_is_reported(self):
        sheet = read_workbook([row("ada@example.com")], sheets=[INSTRUCTIONS], active=1)

        self.assertEqual(sheet.sheet_name, "Members")
        self.assertEqual(sheet.warnings, ['The "Members" sheet was read; it is not the first sheet of the workbook.'])

    def test_a_sheet_called_instructions_is_read_but_flagged(self):
        named = ("Instructions", [HEADERS, row("listed@example.com")])

        sheet = read_workbook([row("ada@example.com")], sheets=[named], active=0)

        self.assertEqual(sheet.sheet_name, "Instructions")
        self.assertEqual(sheet.warnings, ['The sheet read is called "Instructions". Check that it holds the members.'])
        self.assertEqual([parsed["primary_email"] for parsed in sheet.rows], ["listed@example.com"])

    def test_no_sheet_with_a_primary_email_column(self):
        sheet = read(["Name", "Phone"], [["Ada", "2095550101"]])

        self.assertEqual(sheet.error, NO_PRIMARY_EMAIL_COLUMN)
        self.assertEqual((sheet.rows, sheet.sheet_name), ([], ""))

    def test_an_empty_workbook(self):
        sheet = read_upload(BytesIO(workbook_bytes([], [])))

        self.assertEqual(sheet.error, EMPTY_FILE)
        self.assertEqual(sheet.rows, [])

    @patch("apps.authn.services.members.import_.reader.load_workbook", None)
    def test_without_openpyxl_nothing_is_read(self):
        sheet = read(HEADERS, [row("ada@example.com")])

        self.assertEqual((sheet.error, sheet.rows), (NO_OPENPYXL, []))
        self.assertGreater(sheet.file_size, 0)

    def test_a_file_that_is_not_a_workbook(self):
        data = b"Primary Email,First Name\nada@example.com,Ada\n"

        sheet = read_upload(SimpleUploadedFile("members.csv", data, content_type="text/csv"))

        self.assertEqual(sheet.error, UNREADABLE)
        self.assertEqual(sheet.file_name, "members.csv")
        self.assertEqual(sheet.file_size, len(data))
        self.assertEqual(sheet.file_sha256, hashlib.sha256(data).hexdigest())
        self.assertEqual(sheet.rows, [])


class FileIdentityTests(ImportTestCase):
    def test_name_size_and_hash_of_the_upload(self):
        file = upload(HEADERS, [row("ada@example.com")], name="team.xlsx")
        data = file.read()
        file.seek(0)

        sheet = read_upload(file)

        self.assertEqual((sheet.file_name, sheet.file_size), ("team.xlsx", len(data)))
        self.assertEqual(sheet.file_sha256, hashlib.sha256(data).hexdigest())

    def test_a_long_file_name_is_cut_to_255_characters(self):
        file = BytesIO(workbook_bytes(HEADERS, [row("ada@example.com")]))
        file.name = f"{'a' * 300}.xlsx"

        self.assertEqual(read_upload(file).file_name, "a" * 255)

    def test_an_upload_keeps_its_extension_when_the_name_is_long(self):
        sheet = read_upload(upload(HEADERS, [row("ada@example.com")], name=f"{'a' * 300}.xlsx"))

        self.assertEqual(sheet.file_name, f"{'a' * 250}.xlsx")

    def test_a_file_without_a_name(self):
        self.assertEqual(read(HEADERS, [row("ada@example.com")]).file_name, "upload.xlsx")


class ColumnTests(ImportTestCase):
    def test_recognised_informational_and_ignored_columns(self):
        headers = ["Primary Email", "First Name", "Last Updated", "Notes", "Member UUID", None, "Phone"]

        sheet = read(headers, [["ada@example.com", "Ada", "2024-01-01", "note", "", None, "2095550101"]])

        self.assertEqual(
            sheet.columns,
            {
                "recognised": ["Primary Email", "First Name", "Member UUID", "Phone"],
                "informational": ["Last Updated"],
                "ignored": ["Notes"],
                "keys": ["primary_email", "first_name", "member_uuid", "phone_number"],
                "has_member_uuid": True,
            },
        )
        self.assertEqual(sheet.warnings, [])

    def test_header_aliases(self):
        headers = ["email", "Company", "Title - Role (optional)", "UUID", "Date Joined", "firstname", "lastname"]

        sheet = read(headers, [["ada@example.com", "Engines", "Countess", "", "", "Ada", "Lovelace"]])

        self.assertEqual(
            sheet.columns["keys"],
            ["primary_email", "organization", "title", "member_uuid", "when_started", "first_name", "last_name"],
        )
        parsed = sheet.rows[0]
        self.assertEqual((parsed["organization"], parsed["title"]), ("Engines", "Countess"))

    def test_the_template_columns_have_no_member_uuid(self):
        self.assertFalse(read(HEADERS, [row("ada@example.com")]).columns["has_member_uuid"])

    def test_two_columns_with_one_meaning_warn_and_the_last_one_is_read(self):
        sheet = read(["Primary Email", "First Name", "Email"], [["first@example.com", "Ada", "second@example.com"]])

        self.assertEqual(
            sheet.warnings, ['Columns "Primary Email" and "Email" both mean Primary Email; only the last one is read.']
        )
        self.assertEqual(sheet.rows[0]["primary_email"], "second@example.com")
        self.assertEqual(sheet.columns["keys"], ["primary_email", "first_name"])

    def test_repeated_informational_columns_do_not_warn(self):
        sheet = read(["Primary Email", "Last Updated", "last_updated"], [["ada@example.com", "x", "y"]])

        self.assertEqual(sheet.warnings, [])


class RowCapTests(ImportTestCase):
    def test_more_rows_than_the_cap_are_refused(self):
        rows = [row("a@example.com"), row("b@example.com"), row("c@example.com")]

        sheet = read_upload(BytesIO(workbook_bytes(HEADERS, rows)), max_rows=2)

        self.assertEqual(
            sheet.error,
            "The sheet has more than 2 member rows; one import takes at most 2. Split the file and import the parts one after "
            "another.",
        )
        self.assertEqual(sheet.rows, [])

    def test_rows_up_to_the_cap_are_read(self):
        sheet = read_upload(BytesIO(workbook_bytes(HEADERS, [row("a@example.com"), row("b@example.com")])), max_rows=2)

        self.assertEqual(sheet.error, "")
        self.assertEqual(len(sheet.rows), 2)

    def test_blank_rows_are_not_counted_and_rows_keep_their_spreadsheet_number(self):
        blank, spaces = [None] * len(HEADERS), ["   ", *([None] * (len(HEADERS) - 1))]
        rows = [row("a@example.com"), blank, spaces, row("b@example.com")]

        sheet = read_upload(BytesIO(workbook_bytes(HEADERS, rows)), max_rows=2)

        self.assertEqual(sheet.error, "")
        self.assertEqual(
            [(parsed["row"], parsed["primary_email"]) for parsed in sheet.rows],
            [(2, "a@example.com"), (5, "b@example.com")],
        )


class MemberUuidCellTests(ImportTestCase):
    def test_a_uuid_is_read_in_canonical_form_and_the_text_is_kept(self):
        parsed = parse_row(2, {"member_uuid": " 1B4E28BA-2FA1-11D2-883F-0016D3CCA427 "})

        self.assertEqual(parsed["member_uuid"], "1b4e28ba-2fa1-11d2-883f-0016d3cca427")
        self.assertEqual(parsed["member_uuid_text"], "1B4E28BA-2FA1-11D2-883F-0016D3CCA427")

    def test_text_that_is_not_a_uuid(self):
        parsed = parse_row(2, {"member_uuid": "member-17"})

        self.assertEqual((parsed["member_uuid"], parsed["member_uuid_text"]), (None, "member-17"))

    def test_a_blank_cell_or_a_missing_column(self):
        for row_data in ({}, {"member_uuid": None}, {"member_uuid": "   "}):
            with self.subTest(row_data=row_data):
                parsed = parse_row(2, row_data)
                self.assertEqual((parsed["member_uuid"], parsed["member_uuid_text"]), (None, ""))

    def test_the_member_uuid_column_of_a_sheet(self):
        value = uuid.uuid4()

        sheet = read([*HEADERS, "Member UUID"], [[*row("ada@example.com"), str(value)]])

        self.assertEqual(sheet.rows[0]["member_uuid"], str(value))
        self.assertTrue(sheet.columns["has_member_uuid"])


class ParseRowTests(ImportTestCase):
    def test_the_apostrophe_of_our_own_export_is_taken_off(self):
        parsed = parse_row(
            2,
            {
                "primary_email": "'+ada@example.com",
                "secondary_email": "'@ada@example.com",
                "first_name": "'=Bob",
                "last_name": "'+Plus",
                "organization": "'-Minus Inc",
                "title": "'@Lead",
            },
        )

        self.assertEqual(
            [parsed[key] for key in ("primary_email", "secondary_email", "first_name", "last_name")],
            ["+ada@example.com", "@ada@example.com", "=Bob", "+Plus"],
        )
        self.assertEqual((parsed["organization"], parsed["title"]), ("-Minus Inc", "@Lead"))

    def test_other_apostrophes_are_kept(self):
        parsed = parse_row(2, {"first_name": "'Quoted", "last_name": "O'Brien", "title": "'", "organization": "'#1"})

        self.assertEqual(
            [parsed[key] for key in ("first_name", "last_name", "title", "organization")],
            ["'Quoted", "O'Brien", "'", "'#1"],
        )

    def test_phone_cells(self):
        cases = {
            "n/a": None,
            "  ": None,
            None: None,
            2095550101.0: "+2095550101",
            "2095550101.0": "+2095550101",
            "+1 (209) 555-0101": "+12095550101",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(parse_row(2, {"phone_number": value})["phone_number"], expected)

    def test_an_escaped_phone_number_reads_as_the_number(self):
        self.assertEqual(parse_row(2, {"phone_number": "'+1 (209) 555-0101"})["phone_number"], "+12095550101")

    def test_an_unreadable_when_started_date_is_a_v6_warning(self):
        parsed = parse_row(2, {"when_started": "someday"})

        self.assertIsNone(parsed["date_joined"])
        text = "When Started cell 'someday' is not a date; it was ignored"
        self.assertEqual(parsed["warnings"], [{"code": "V6", "text": text}])
        self.assertEqual(parsed["notes"], [text])

    def test_readable_when_started_dates(self):
        for value in ("2024-01-15", "01/15/2024", "2024-01-15 09:30", datetime(2024, 1, 15, 9, 30)):
            with self.subTest(value=value):
                parsed = parse_row(2, {"when_started": value})
                self.assertEqual(timezone.localtime(parsed["date_joined"]).date(), date(2024, 1, 15))
                self.assertTrue(timezone.is_aware(parsed["date_joined"]))
                self.assertEqual(parsed["warnings"], [])

    def test_a_blank_when_started_cell_has_no_warning(self):
        parsed = parse_row(2, {"when_started": "  "})

        self.assertEqual((parsed["date_joined"], parsed["warnings"]), (None, []))

    def test_unrecognised_true_false_text_is_a_v5_warning_and_counts_as_blank(self):
        parsed = parse_row(
            2, {"primary_verified": "maybe", "is_active": "yes", "is_staff": "N/A", "phone_verified": ""}
        )

        self.assertEqual((parsed["primary_verified"], parsed["is_active"], parsed["is_staff"]), (None, True, None))
        self.assertIsNone(parsed["phone_verified"])
        self.assertEqual(
            parsed["warnings"],
            [
                {"code": "V5", "text": "Staff cell 'N/A' is not TRUE or FALSE; it was ignored"},
                {"code": "V5", "text": "Primary Verified cell 'maybe' is not TRUE or FALSE; it was ignored"},
            ],
        )

    def test_true_false_cells(self):
        cases = [(True, True), (False, False), (1, True), (0.0, False), (2, None), ("Inactive", False)]
        cases += [(" Y ", True), ("active", True), (None, None), ("", None)]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertIs(parse_flag(value), expected)

    def test_raw_keeps_every_imported_cell_as_typed(self):
        parsed = parse_row(
            2,
            {
                "primary_email": " ada@example.com ",
                "first_name": None,
                "is_active": True,
                "is_staff": False,
                "phone_number": 2095550101.0,
                "when_started": datetime(2024, 1, 15, 9, 30),
                "title": date(2024, 1, 15),
                "last_updated": "2024-02-01",
                "notes": "not imported",
            },
        )

        self.assertEqual(
            parsed["raw"],
            {
                "primary_email": "ada@example.com",
                "first_name": "",
                "is_active": "TRUE",
                "is_staff": "FALSE",
                "phone_number": "2095550101",
                "when_started": "2024-01-15 09:30",
                "title": "2024-01-15",
            },
        )

    def test_cell_text_of_other_numbers(self):
        self.assertEqual((cell_text(2.5), cell_text(7), cell_text("  x ")), ("2.5", "7", "x"))

    def test_raw_cells_of_a_sheet(self):
        headers = ["Primary Email", "Phone Number", "Active", "Primary Verified"]

        sheet = read(headers, [["Ada@Example.com ", 2095550101, True, "maybe"]])

        self.assertEqual(
            sheet.rows[0]["raw"],
            {
                "primary_email": "Ada@Example.com",
                "phone_number": "2095550101",
                "is_active": "TRUE",
                "primary_verified": "maybe",
            },
        )

    def test_column_presence_is_kept_apart_from_blank_cells(self):
        present = parse_row(2, {"primary_email": "ada@example.com", "secondary_email": None, "phone_number": ""})
        missing = parse_row(2, {"primary_email": "ada@example.com"})

        self.assertEqual((present["secondary_email"], present["phone_number"]), (None, None))
        self.assertTrue(present["has_secondary_email_column"] and present["has_phone_column"])
        self.assertFalse(missing["has_secondary_email_column"] or missing["has_phone_column"])
