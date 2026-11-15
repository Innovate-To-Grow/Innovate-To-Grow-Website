from io import BytesIO

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from openpyxl import load_workbook

from apps.authn.models import ContactEmail, ContactPhone, Member
from apps.authn.services.members.export.excel import export_members_to_excel
from apps.authn.services.members.import_ import generate_template_excel, import_members_from_excel
from apps.authn.services.members.import_.review.apply.execute import execute_update
from apps.authn.services.members.import_.review.lookup import load_snapshot
from apps.authn.services.members.import_.review.plan import plan_row
from apps.authn.services.members.import_.review.plan.actions import UPDATE, Action
from apps.authn.services.members.import_.workbook.parsing import PHONE_VERIFIED_IGNORED, parse_row
from apps.authn.tests.services.members.import_safety.test_import_members_phone_verified import (
    CELLS,
    _number,
    _row,
    _sheet,
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
