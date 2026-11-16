from django.core.cache import cache
from django.test import TestCase

from apps.authn.models import ContactEmail, ContactPhone
from apps.authn.services.members.import_ import import_members_from_excel
from apps.authn.services.members.import_.parsing import (
    PHONE_VERIFIED_IGNORED,
)
from apps.authn.tests.services.members.import_safety.test_import_members_phone_verified import (
    CELLS,
    _number,
    _row,
    _sheet,
)

from ..import_sheets import build_sheet


class NewMemberPhoneTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_every_cell_value_saves_a_new_members_number_unverified(self):
        rows = [
            _row(f"new{index}@example.com", {"Phone Number": f"+1{_number(index)}", "Phone Verified": cell})
            for index, cell in enumerate(CELLS)
        ]

        result = import_members_from_excel(_sheet(rows))

        self.assertTrue(result.success)
        self.assertEqual(result.created_count, len(CELLS))
        self.assertEqual(ContactPhone.objects.count(), len(CELLS))
        self.assertFalse(ContactPhone.objects.filter(verified=True).exists())
        # One note for the file, however many rows; no row is told its cell "is not TRUE or FALSE".
        self.assertEqual(result.warnings, [PHONE_VERIFIED_IGNORED])
        self.assertEqual(result.errors, [])

    def test_the_sheets_email_flags_and_phone_subscribed_still_apply_to_a_new_member(self):
        result = import_members_from_excel(
            _sheet(
                [
                    _row(
                        "ada@example.com",
                        {
                            "Primary Verified": "TRUE",
                            "Phone Number": "+12095550001",
                            "Phone Subscribed": "TRUE",
                            "Phone Verified": "TRUE",
                        },
                    )
                ]
            )
        )

        self.assertEqual(result.created_count, 1)
        self.assertTrue(ContactEmail.objects.get(email_address="ada@example.com").verified)
        phone = ContactPhone.objects.get(phone_number="2095550001")
        self.assertEqual((phone.verified, phone.subscribe), (False, True))

    def test_without_the_column_the_number_is_unverified_and_nothing_is_said(self):
        result = import_members_from_excel(
            build_sheet(
                ["Primary Email", "First Name", "Last Name", "Phone Number"],
                [["ada@example.com", "Ada", "Lovelace", "+12095550001"]],
            )
        )

        self.assertEqual(result.created_count, 1)
        self.assertFalse(ContactPhone.objects.get(phone_number="2095550001").verified)
        self.assertEqual(result.warnings, [])

    def test_an_alias_header_is_ignored_and_reported_too(self):
        result = import_members_from_excel(
            build_sheet(
                ["Primary Email", "First Name", "Last Name", "Phone", "Phone Number Verified"],
                [["ada@example.com", "Ada", "Lovelace", "+12095550001", "TRUE"]],
            )
        )

        self.assertFalse(ContactPhone.objects.get(phone_number="2095550001").verified)
        self.assertEqual(result.warnings, [PHONE_VERIFIED_IGNORED])

    def test_the_note_is_given_even_when_no_row_is_imported(self):
        result = import_members_from_excel(
            _sheet([_row(None, {"Phone Verified": "TRUE"}), _row("", {"Phone Verified": "FALSE"})])
        )

        self.assertEqual(result.created_count, 0)
        self.assertEqual(result.warnings, [PHONE_VERIFIED_IGNORED])
        self.assertEqual(result.errors, ["Row 2: Missing primary email", "Row 3: Missing primary email"])

    def test_the_file_note_comes_before_the_row_notes(self):
        result = import_members_from_excel(
            _sheet(
                [
                    _row("ada@example.com", {"Phone Number": "+12095550001", "Phone Verified": "TRUE"}),
                    _row("bob@example.com", {"Phone Number": "+12095550001", "Phone Verified": "TRUE"}),
                ]
            )
        )

        self.assertEqual(result.created_count, 2)
        self.assertEqual(
            result.warnings,
            [
                PHONE_VERIFIED_IGNORED,
                "Row 3: Phone Number +12095550001 is also in row 2; only that row can add it; if that row is skipped, no row adds it",
            ],
        )
