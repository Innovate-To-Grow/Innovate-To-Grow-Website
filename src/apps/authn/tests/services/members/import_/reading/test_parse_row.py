from datetime import date, datetime

from django.utils import timezone

from apps.authn.services.members.import_.workbook.parsing import cell_text, parse_flag, parse_row
from apps.authn.tests.services.members.import_.helpers import (
    ImportTestCase,
    read,
)


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
        parsed = parse_row(2, {"primary_verified": "maybe", "is_active": "yes", "admin": "N/A", "phone_verified": ""})

        self.assertEqual((parsed["primary_verified"], parsed["is_active"]), (None, True))
        # The Phone Verified and Admin columns are ignored: not parsed, never a V5 warning.
        self.assertNotIn("phone_verified", parsed)
        self.assertNotIn("admin", parsed)
        self.assertEqual(
            parsed["warnings"],
            [{"code": "V5", "text": "Primary Verified cell 'maybe' is not TRUE or FALSE; it was ignored"}],
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
                "admin": False,
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
