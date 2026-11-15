"""The guards around risky changes: the last verified sign-in contact, phone-only members, and the safe direction.

A single item that would remove or un-verify a member's only verified sign-in contact can't be ticked. Ticks that are
each allowed but together would leave a member without one are a plan problem: ``run_import`` raises ``RowWriteError``
before it writes anything, so the whole import is refused. Verifying and unsubscribing need no tick.
"""

from django.db import transaction

from apps.authn.models import ContactEmail, ContactPhone, Member
from apps.authn.services.members.import_.review.apply.execute import RowWriteError
from apps.authn.services.members.import_.review.staging.selection import selection_problems
from apps.authn.tests.services.members.import_.helpers import HEADERS, ImportTestCase, row

UUID_HEADERS = [*HEADERS, "Member UUID"]


class LastVerifiedContactTests(ImportTestCase):
    def setUp(self):
        super().setUp()
        self.primary = self.ada.contact_emails.get()
        self.mobile = self.phone(self.ada, "2095550101", verified=True)
        self.label = f"Ada Lovelace (member {self.ada.pk})"

    def items(self, analysis) -> dict:
        return {item["id"]: item for item in analysis.risky[str(self.ada.pk)]}

    def test_ticks_that_together_remove_the_last_verified_contact_refuse_the_whole_import(self):
        rows = [
            row("new@example.com", First_Name="Nina", Last_Name="New"),
            row("ada@example.com", Primary_Verified="FALSE"),
        ]
        ticks = [f"R6:{self.primary.pk}", f"R3:{self.mobile.pk}"]
        items = self.items(self.analyse(rows)[1])
        self.assertTrue(all(items[tick]["enabled"] for tick in ticks))

        with self.assertRaisesMessage(
            RowWriteError,
            f"Row 3: These ticks would remove the last verified sign-in contact of {self.label}; untick one of them",
        ) as caught:
            with transaction.atomic():
                self.apply(rows, {3: ("update", ticks)})

        self.assertEqual(caught.exception.row_number, 3)
        self.assertFalse(ContactEmail.objects.filter(email_address="new@example.com").exists())
        self.assertFalse(Member.objects.filter(first_name="Nina").exists())
        self.primary.refresh_from_db()
        self.assertTrue(self.primary.verified)
        self.assertTrue(ContactPhone.objects.filter(pk=self.mobile.pk).exists())

    def test_two_removals_that_together_remove_the_last_verified_contact(self):
        ContactEmail.objects.filter(pk=self.primary.pk).update(verified=False)
        work = self.email(self.ada, "ada.work@example.com", verified=True)
        ticks = [f"R1:{work.pk}", f"R3:{self.mobile.pk}"]
        items = self.items(self.analyse_one(row("ada@example.com")))
        self.assertTrue(all(items[tick]["enabled"] for tick in ticks))

        with self.assertRaises(RowWriteError):
            with transaction.atomic():
                self.apply([row("ada@example.com")], {2: ("update", ticks)})

        self.assertEqual(self.ada.contact_emails.count(), 2)
        self.assertTrue(ContactPhone.objects.filter(pk=self.mobile.pk).exists())

    def test_one_of_those_ticks_alone_is_applied(self):
        (outcome,) = self.apply([row("ada@example.com")], {2: ("update", [f"R3:{self.mobile.pk}"])})

        self.assertEqual(outcome.outcome, "updated")
        self.assertFalse(ContactPhone.objects.filter(pk=self.mobile.pk).exists())
        self.primary.refresh_from_db()
        self.assertTrue(self.primary.verified)

    def test_selection_problems_name_the_row_and_the_member(self):
        analyses = self.analyse([row("ada@example.com", Primary_Verified="FALSE")])

        problems = selection_problems(analyses, {2: ("update", [f"R6:{self.primary.pk}", f"R3:{self.mobile.pk}"])})

        self.assertEqual(
            problems,
            [f"Row 2: These ticks would remove the last verified sign-in contact of {self.label}; untick one of them"],
        )

    def test_a_member_without_any_verified_contact_is_not_blocked(self):
        ContactEmail.objects.filter(pk=self.primary.pk).update(verified=False)
        ContactPhone.objects.filter(pk=self.mobile.pk).update(verified=False)

        (outcome,) = self.apply([row("ada@example.com")], {2: ("update", [f"R3:{self.mobile.pk}"])})

        self.assertEqual(outcome.outcome, "updated")
        self.assertFalse(ContactPhone.objects.filter(pk=self.mobile.pk).exists())


class PhoneOnlyMemberTests(ImportTestCase):
    """A member whose only sign-in contact is a verified phone, matched by Member UUID."""

    def setUp(self):
        super().setUp()
        self.pat = Member.objects.create_user(password="StrongPass123!", first_name="Pat", last_name="Phone")
        self.only = self.phone(self.pat, "2095550111", verified=True)

    def pat_row(self, **cells):
        return [*row("pat.new@example.com", First_Name="Pat", Last_Name="Phone", **cells), str(self.pat.pk)]

    def items(self, analysis) -> dict:
        return {item["id"]: item for item in analysis.risky[str(self.pat.pk)]}

    def test_the_phone_can_be_neither_removed_nor_unverified(self):
        reason = "It is the only verified sign-in contact of Pat Phone"

        blank = self.analyse_one(self.pat_row(), UUID_HEADERS)
        named = self.analyse_one(self.pat_row(Phone_Number="2095550111", Phone_Verified="FALSE"), UUID_HEADERS)
        replaced = self.analyse_one(self.pat_row(Phone_Number="2095550122"), UUID_HEADERS)

        self.assertEqual((blank.status, blank.facts["matched_by"]), ("no_change", "uuid"))
        self.assertEqual(self.items(blank)[f"R3:{self.only.pk}"]["reason"], reason)
        # Phone Verified FALSE is ignored: a phone number has no un-verify item at all.
        self.assertEqual(named.risky.get(str(self.pat.pk), []), [])
        self.assertEqual(self.items(replaced)[f"R4:{self.only.pk}"]["reason"], reason)

    def test_a_forced_tick_is_refused_and_the_phone_stays(self):
        with self.assertRaisesMessage(
            RowWriteError, "Row 2: These ticks would remove the last verified sign-in contact"
        ):
            with transaction.atomic():
                self.apply([self.pat_row()], {2: ("update", [f"R3:{self.only.pk}"])}, UUID_HEADERS)

        self.only.refresh_from_db()
        self.assertTrue(self.only.verified)

    def test_the_sheet_address_is_not_added_and_a_new_number_starts_unverified(self):
        (outcome,) = self.apply([self.pat_row(Phone_Number="2095550122", Phone_Verified="TRUE")], headers=UUID_HEADERS)

        self.assertEqual(outcome.outcome, "updated")
        self.assertFalse(self.pat.contact_emails.exists())
        self.assertEqual(
            sorted(self.pat.contact_phones.values_list("phone_number", "verified")),
            [("2095550111", True), ("2095550122", False)],
        )
        self.assertIn(
            f"Primary Email pat.new@example.com is not one of the member's addresses; it is not added to Pat Phone "
            f"(member {self.pat.pk}), and its Verified/Subscribed cells are ignored",
            outcome.notes,
        )
