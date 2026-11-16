"""Tests for the member import template generator and parsing helpers."""

from datetime import datetime
from io import BytesIO

from django.test import TestCase
from django.utils import timezone

from apps.authn.services.members.import_.parsing import (
    clean_phone,
    generate_random_password,
    normalize_header,
    parse_date,
    parse_flag,
    parse_row,
)
from apps.authn.services.members.import_.template import generate_template_excel

try:
    from openpyxl import load_workbook
except ImportError:  # pragma: no cover - test env should include openpyxl
    load_workbook = None


class GenerateTemplateExcelTests(TestCase):
    def test_template_is_valid_workbook_with_headers_and_instructions(self):
        data = generate_template_excel()
        self.assertIsInstance(data, bytes)
        self.assertGreater(len(data), 0)

        workbook = load_workbook(filename=BytesIO(data))
        self.assertIn("Members", workbook.sheetnames)
        self.assertIn("Instructions", workbook.sheetnames)

        members_sheet = workbook["Members"]
        header_values = [cell.value for cell in members_sheet[1]]
        self.assertIn("Primary Email", header_values)
        self.assertIn("Phone Number", header_values)

        # Example row populated on row 2
        example_first = members_sheet.cell(row=2, column=1).value
        self.assertEqual(example_first, "John")

        instructions = workbook["Instructions"]
        self.assertEqual(instructions.cell(row=1, column=1).value, "Field Descriptions")


class ParsingHelperTests(TestCase):
    def test_generate_random_password_length_and_charset(self):
        pw = generate_random_password(16)
        self.assertEqual(len(pw), 16)

    def test_normalize_header_empty(self):
        self.assertEqual(normalize_header(""), "")

    def test_normalize_header_maps_known_alias(self):
        self.assertEqual(normalize_header("Primary Email"), "primary_email")

    def test_normalize_header_unknown_lowercased(self):
        self.assertEqual(normalize_header("Some Random"), "some random")

    def test_parse_flag_variants(self):
        self.assertIs(parse_flag(True), True)
        self.assertIs(parse_flag(False), False)
        self.assertIs(parse_flag("yes"), True)
        self.assertIs(parse_flag(" TRUE "), True)
        self.assertIs(parse_flag("Y"), True)
        self.assertIs(parse_flag("active"), True)
        self.assertIs(parse_flag("no"), False)
        self.assertIs(parse_flag("FALSE"), False)
        self.assertIs(parse_flag("inactive"), False)
        self.assertIs(parse_flag(1), True)
        self.assertIs(parse_flag(0), False)
        self.assertIs(parse_flag(1.0), True)
        self.assertIs(parse_flag(0.0), False)

    def test_parse_flag_blank_or_unrecognised_is_none(self):
        """Unrecognised text used to count as FALSE and so un-verified or unsubscribed contacts."""
        for value in (None, "", "   ", "N/A", "x", "maybe", 2, 0.5):
            with self.subTest(value=value):
                self.assertIsNone(parse_flag(value))

    def test_parse_row_reports_unrecognised_flag_text(self):
        row = parse_row(
            4,
            {
                "primary_email": "a@example.com",
                "primary_subscribed": "N/A",
                "primary_verified": "   ",
                "is_active": "yes",
            },
        )
        self.assertIsNone(row["primary_subscribed"])
        self.assertIsNone(row["primary_verified"])
        self.assertTrue(row["is_active"])
        self.assertEqual(row["notes"], ["Primary Subscribed cell 'N/A' is not TRUE or FALSE; it was ignored"])

    def test_parse_row_records_which_contact_columns_exist(self):
        row = parse_row(2, {"primary_email": "a@example.com", "secondary_email": None, "phone_number": None})
        self.assertTrue(row["has_secondary_email_column"])
        self.assertTrue(row["has_phone_column"])
        self.assertFalse(parse_row(2, {"primary_email": "a@example.com"})["has_phone_column"])

    def test_parse_date_none(self):
        self.assertIsNone(parse_date(None))

    def test_parse_date_naive_datetime_made_aware(self):
        result = parse_date(datetime(2024, 1, 15, 10, 30))
        self.assertTrue(timezone.is_aware(result))

    def test_parse_date_aware_datetime_passthrough(self):
        aware = timezone.make_aware(datetime(2024, 1, 15, 10, 30))
        self.assertEqual(parse_date(aware), aware)

    def test_parse_date_empty_string(self):
        self.assertIsNone(parse_date("   "))

    def test_parse_date_recognizes_format(self):
        result = parse_date("2024-01-15")
        self.assertEqual(result.year, 2024)
        self.assertEqual(result.month, 1)
        self.assertEqual(result.day, 15)

    def test_parse_date_unrecognized_returns_none(self):
        self.assertIsNone(parse_date("not-a-date"))

    def test_clean_phone_none(self):
        self.assertIsNone(clean_phone(None))

    def test_clean_phone_empty(self):
        self.assertIsNone(clean_phone("   "))

    def test_clean_phone_strips_trailing_dot_zero(self):
        self.assertEqual(clean_phone("12095551234.0"), "+12095551234")

    def test_clean_phone_no_digits_returns_none(self):
        self.assertIsNone(clean_phone("abc"))

    def test_clean_phone_with_plus(self):
        self.assertEqual(clean_phone("+1 (209) 555-1234"), "+12095551234")

    def test_clean_phone_without_plus(self):
        self.assertEqual(clean_phone("2095551234"), "+2095551234")

    def test_parse_row_full(self):
        row = parse_row(
            5,
            {
                "primary_email": " Main@Example.com ",
                "first_name": " Ada ",
                "last_name": " Lovelace ",
                "secondary_email": "alt@example.com",
                "is_active": "yes",
                "is_staff": "no",
                "when_started": "2024-01-15",
                "phone_number": "+12095551234",
            },
        )
        self.assertEqual(row["row"], 5)
        self.assertEqual(row["primary_email"], "Main@Example.com")
        self.assertEqual(row["first_name"], "Ada")
        self.assertTrue(row["is_active"])
        self.assertFalse(row["is_staff"])
        self.assertEqual(row["phone_number"], "+12095551234")

    def test_parse_row_minimal_defaults(self):
        row = parse_row(2, {})
        self.assertIsNone(row["primary_email"])
        self.assertEqual(row["first_name"], "")
        self.assertIsNone(row["is_active"])
        self.assertIsNone(row["is_staff"])
        self.assertIsNone(row["phone_number"])
        self.assertEqual(row["notes"], [])
