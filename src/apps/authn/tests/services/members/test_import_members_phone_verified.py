"""The member import ignores the Phone Verified column.

A verified phone number is a sign-in factor, so only the member's own one-time code may produce one. An import saves
every number it adds unverified, whatever the sheet says, and never changes the status of a number already stored
(verified stays verified, unverified stays unverified). A sheet may still have the column (Export to Excel writes it):
it is accepted, ignored, and reported once for the file.
"""

from io import BytesIO

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from openpyxl import load_workbook

from apps.authn.models import ContactEmail, ContactPhone, Member
from apps.authn.services.members.export_excel import export_members_to_excel
from apps.authn.services.members.import_ import generate_template_excel, import_members_from_excel
from apps.authn.services.members.import_.parsing import (
    FLAG_COLUMNS,
    IGNORED_COLUMNS,
    PHONE_VERIFIED_IGNORED,
    column_notes,
    normalize_header,
    parse_row,
)
from apps.authn.services.members.import_.review.actions import UPDATE, Action
from apps.authn.services.members.import_.review.execute import execute_update
from apps.authn.services.members.import_.review.lookup import load_snapshot
from apps.authn.services.members.import_.review.plan import plan_row
from apps.authn.services.members.import_.types import ImportResult

from .import_sheets import PHONE_VERIFIED_HEADERS, build_sheet, full_row

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


class ExistingMemberPhoneTests(TestCase):
    def setUp(self):
        cache.clear()
        self.member = Member.objects.create_user(
            password="StrongPass123!", first_name="Ada", last_name="Lovelace", is_active=True
        )
        ContactEmail.objects.create(
            member=self.member, email_address="ada@example.com", email_type="primary", verified=True
        )

    def _phone(self, number="2095550001", **flags):
        return ContactPhone.objects.create(member=self.member, phone_number=number, region="1-US", **flags)

    def _update(self, cells):
        return import_members_from_excel(_sheet([_row("ada@example.com", cells)]), update_existing=True)

    def test_a_new_number_on_an_existing_member_is_unverified_for_every_cell_value(self):
        for index, cell in enumerate(CELLS):
            with self.subTest(cell=cell):
                number = _number(index)

                result = self._update({"Phone Number": f"+1{number}", "Phone Verified": cell})

                self.assertEqual(result.updated_count, 1)
                self.assertFalse(ContactPhone.objects.get(phone_number=number).verified)
                self.assertEqual(result.warnings[0], PHONE_VERIFIED_IGNORED)
                self.assertFalse(any("Phone Verified" in note for note in result.warnings[1:]))
                self.assertFalse(any("added unverified" in note for note in result.warnings))

    def test_a_stored_verified_number_stays_verified_whatever_the_cell_says(self):
        phone = self._phone(verified=True, subscribe=True)
        for cell in CELLS:
            with self.subTest(cell=cell):
                result = self._update({"Phone Number": "+12095550001", "Phone Verified": cell})

                phone.refresh_from_db()
                self.assertTrue(phone.verified)
                self.assertEqual(result.warnings, [PHONE_VERIFIED_IGNORED])

    def test_a_stored_unverified_number_stays_unverified_whatever_the_cell_says(self):
        phone = self._phone(verified=False, subscribe=True)
        for cell in CELLS:
            with self.subTest(cell=cell):
                result = self._update({"Phone Number": "+12095550001", "Phone Verified": cell})

                phone.refresh_from_db()
                self.assertFalse(phone.verified)
                self.assertEqual(result.warnings, [PHONE_VERIFIED_IGNORED])

    def test_phone_subscribed_is_still_reported_for_a_stored_number_but_phone_verified_never(self):
        self._phone(verified=False, subscribe=False)

        result = self._update({"Phone Number": "+12095550001", "Phone Subscribed": "TRUE", "Phone Verified": "TRUE"})

        self.assertEqual(
            result.warnings,
            [
                PHONE_VERIFIED_IGNORED,
                "Row 2: Phone Subscribed is TRUE, but +12095550001 is unsubscribed; left unsubscribed (re-subscribing "
                "needs the person's consent and its tick)",
            ],
        )

    def test_a_blank_number_cell_keeps_every_number_with_its_status(self):
        verified = self._phone("2095550001", verified=True)
        unverified = self._phone("2095550002", verified=False)

        result = self._update({"Phone Verified": "FALSE"})

        verified.refresh_from_db()
        unverified.refresh_from_db()
        self.assertEqual((verified.verified, unverified.verified), (True, False))
        self.assertEqual(result.warnings[0], PHONE_VERIFIED_IGNORED)

    def test_a_stale_phone_verified_value_in_stored_row_values_is_never_read(self):
        """A row planned from values that still carry the old key (a batch staged before the change) can't verify."""
        parsed = parse_row(2, {"primary_email": "ada@example.com", "phone_number": "+12095550009"})
        parsed["phone_verified"] = True
        snapshot = load_snapshot([parsed])

        plan = plan_row(parsed, Action(UPDATE, target=str(self.member.pk)), snapshot)
        execute_update(2, plan, self.member)

        self.assertFalse(ContactPhone.objects.get(phone_number="2095550009").verified)
        self.assertIn("Adds phone +12095550009 (unverified, not subscribed)", plan.changes)
        self.assertEqual(plan.notes, [])

    def test_an_export_round_trip_keeps_every_numbers_status(self):
        verified = self._phone("2095550001", verified=True)
        other = Member.objects.create_user(password="StrongPass123!", first_name="Bob", last_name="Ross")
        ContactEmail.objects.create(member=other, email_address="bob@example.com", email_type="primary")
        unverified = ContactPhone.objects.create(member=other, phone_number="2095550002", region="1-US")
        exported = export_members_to_excel(Member.objects.filter(pk__in=[self.member.pk, other.pk]))
        sheet = load_workbook(BytesIO(exported)).active
        self.assertIn("Phone Verified", [cell.value for cell in sheet[1]])

        result = import_members_from_excel(BytesIO(exported), update_existing=True)

        verified.refresh_from_db()
        unverified.refresh_from_db()
        self.assertEqual((verified.verified, unverified.verified), (True, False))
        self.assertEqual(result.warnings[0], PHONE_VERIFIED_IGNORED)
        self.assertEqual(result.updated_count, 2)


class TemplateTests(SimpleTestCase):
    def test_the_template_has_no_phone_verified_column_and_says_why(self):
        workbook = load_workbook(BytesIO(generate_template_excel()))
        members = workbook["Members"]
        headers = [cell.value for cell in members[1]]
        example = dict(zip(headers, (cell.value for cell in members[2]), strict=True))

        self.assertNotIn("Phone Verified", headers)
        self.assertEqual((example["Phone Number"], example["Phone Subscribed"]), ("+12095551234", "TRUE"))
        self.assertEqual(example["Organization (optional)"], "UC Merced")
        instructions = [row[1] for row in workbook["Instructions"].iter_rows(values_only=True) if row[1]]
        self.assertTrue(any("Phone Verified column" in text and "is ignored" in text for text in instructions))
        self.assertFalse(any("Whether the phone is verified" in text for text in instructions))
