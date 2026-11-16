import uuid
from io import BytesIO

from apps.authn.services.members.import_.parsing import parse_row
from apps.authn.services.members.import_.reader import (
    read_upload,
)
from apps.authn.tests.services.members.import_.helpers import (
    HEADERS,
    ImportTestCase,
    read,
    row,
    workbook_bytes,
)


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
                "notes": [],
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
