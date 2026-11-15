"""Reading an upload: which worksheet is read, its columns, the row cap, and what ``parse_row`` adds to each row."""

import hashlib
from io import BytesIO
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile

from apps.authn.services.members.import_.workbook.reader import (
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

    @patch("apps.authn.services.members.import_.workbook.reader.load_workbook", None)
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
