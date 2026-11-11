"""The guards around risky changes: the last verified sign-in contact, phone-only members, and the safe direction.

A single item that would remove or un-verify a member's only verified sign-in contact can't be ticked. Ticks that are
each allowed but together would leave a member without one are a plan problem: ``run_import`` raises ``RowWriteError``
before it writes anything, so the whole import is refused. Verifying and unsubscribing need no tick.
"""

from django.core import mail
from django.db import transaction

from apps.authn.models import ContactEmail, ContactPhone, Member
from apps.authn.services.members.import_.review.execute import RowWriteError
from apps.authn.services.members.import_.review.selection import selection_problems
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
        self.assertEqual(self.items(named)[f"R6:{self.only.pk}"]["reason"], reason)
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


class SafeDirectionTests(ImportTestCase):
    """TRUE verifies and FALSE unsubscribes a contact the row names, without a tick, when the member owns it."""

    def setUp(self):
        super().setUp()
        self.primary = self.ada.contact_emails.get()
        self.work = self.email(self.ada, "ada.work@example.com", verified=False, subscribe=True)
        self.mobile = self.phone(self.ada, "2095550101", verified=False, subscribe=True)
        self.named = {"Secondary_Email": "ada.work@example.com", "Phone_Number": "2095550101"}

    def test_verified_true_verifies_only_with_its_tick(self):
        """A verified contact is a sign-in factor, so marking one verified is its own tick (R9), off by default."""
        cells_row = row("ada@example.com", Secondary_Verified="TRUE", Phone_Verified="TRUE", **self.named)

        analysis = self.analyse_one(cells_row)
        (unticked,) = self.apply([cells_row])

        items = {item["code"]: item for item in analysis.risky[str(self.ada.pk)]}
        self.assertEqual((analysis.status, sorted(items)), ("no_change", ["R9"]))
        self.assertEqual(unticked.outcome, "no_change")
        self.work.refresh_from_db()
        self.mobile.refresh_from_db()
        self.assertEqual((self.work.verified, self.mobile.verified), (False, False))

        (ticked,) = self.apply([cells_row], {2: ("update", [f"R9:{self.work.pk}", f"R9:{self.mobile.pk}"])})

        self.assertEqual(ticked.outcome, "updated")
        self.work.refresh_from_db()
        self.mobile.refresh_from_db()
        self.assertEqual((self.work.verified, self.mobile.verified), (True, True))
        self.assertIn("Marks ada.work@example.com verified", ticked.changes)
        self.assertIn("Marks +12095550101 verified", ticked.changes)

    def test_subscribed_false_unsubscribes_without_a_tick(self):
        cells = {"Primary_Subscribed": "FALSE", "Secondary_Subscribed": "FALSE", "Phone_Subscribed": "FALSE"}

        (outcome,) = self.apply([row("ada@example.com", **cells, **self.named)])

        for contact in (self.primary, self.work, self.mobile):
            contact.refresh_from_db()
        self.assertEqual((self.primary.subscribe, self.work.subscribe, self.mobile.subscribe), (False, False, False))
        self.assertIn("Unsubscribes ada@example.com", outcome.changes)

    def test_the_flag_cells_of_another_members_contacts_are_ignored(self):
        grace = self.member("Grace", "Hopper", "grace@example.com")
        theirs = self.email(grace, "grace.work@example.com", verified=False, subscribe=True)
        phone = self.phone(grace, "2095550177", verified=False, subscribe=True)
        cells = {"Secondary_Verified": "TRUE", "Secondary_Subscribed": "FALSE", "Phone_Verified": "TRUE"}
        cells_row = row("ada@example.com", Secondary_Email="grace.work@example.com", Phone_Number="2095550177", **cells)

        (outcome,) = self.apply([cells_row])

        self.assertEqual(outcome.outcome, "no_change")
        theirs.refresh_from_db()
        phone.refresh_from_db()
        self.assertEqual((theirs.member, theirs.verified, theirs.subscribe), (grace, False, True))
        self.assertEqual((phone.member, phone.verified), (grace, False))

    def test_a_new_member_trusts_the_sheet_flags(self):
        cells = {
            "Primary_Verified": "TRUE",
            "Primary_Subscribed": "FALSE",
            "Secondary_Email": "nina.work@example.com",
            "Secondary_Verified": "TRUE",
            "Phone_Number": "2095550155",
            "Phone_Verified": "TRUE",
            "Phone_Subscribed": "TRUE",
        }

        (outcome,) = self.apply([row("nina@example.com", First_Name="Nina", Last_Name="New", **cells)])

        self.assertEqual(outcome.outcome, "created")
        emails = {c.email_address: (c.email_type, c.verified, c.subscribe) for c in outcome.member.contact_emails.all()}
        self.assertEqual(
            emails,
            {"nina@example.com": ("primary", True, False), "nina.work@example.com": ("secondary", True, True)},
        )
        self.assertEqual(
            list(outcome.member.contact_phones.values_list("phone_number", "verified", "subscribe")),
            [("2095550155", True, True)],
        )
        self.assertEqual(mail.outbox, [])


class SubscriptionConsentTests(ImportTestCase):
    """A contact added to an existing member is never subscribed on a channel the member opted out of."""

    def setUp(self):
        super().setUp()
        ContactEmail.objects.filter(email_address="ada@example.com").update(subscribe=False)

    def test_a_new_secondary_is_added_unsubscribed_when_every_address_is_unsubscribed(self):
        cells_row = row("ada@example.com", Secondary_Email="ada.new@example.com", Secondary_Subscribed="TRUE")

        (outcome,) = self.apply([cells_row])

        self.assertFalse(ContactEmail.objects.get(email_address="ada.new@example.com").subscribe)
        self.assertIn(
            "ada.new@example.com is added unsubscribed: the member is unsubscribed at every other address "
            "(re-subscribing needs the person's consent)",
            outcome.notes,
        )

    def test_without_a_subscribed_cell_it_is_added_unsubscribed_silently(self):
        (outcome,) = self.apply([row("ada@example.com", Secondary_Email="ada.new@example.com")])

        self.assertFalse(ContactEmail.objects.get(email_address="ada.new@example.com").subscribe)
        self.assertFalse(any("added unsubscribed" in note for note in outcome.notes))

    def test_a_new_number_is_added_unsubscribed_when_every_number_is_unsubscribed(self):
        self.phone(self.ada, "2095550101", subscribe=False)

        (outcome,) = self.apply([row("ada@example.com", Phone_Number="2095550199", Phone_Subscribed="TRUE")])

        self.assertFalse(ContactPhone.objects.get(phone_number="2095550199").subscribe)
        self.assertIn(
            "+12095550199 is added unsubscribed: the member's other phone numbers are unsubscribed (re-subscribing "
            "needs the person's consent)",
            outcome.notes,
        )

    def test_a_first_number_takes_the_sheet_value(self):
        self.apply([row("ada@example.com", Phone_Number="2095550199", Phone_Subscribed="TRUE")])

        self.assertTrue(ContactPhone.objects.get(phone_number="2095550199").subscribe)

    def test_an_attached_address_is_unsubscribed_when_every_address_is_unsubscribed(self):
        loose = ContactEmail.objects.create(member=None, email_address="loose@example.com", subscribe=True)
        cells_row = row("loose@example.com", Secondary_Email="ada@example.com", Primary_Subscribed="TRUE")

        (outcome,) = self.apply([cells_row], {2: (f"attach_to:{self.ada.pk}", [])})

        loose.refresh_from_db()
        self.assertEqual((loose.member, loose.subscribe), (self.ada, False))
        self.assertIn(
            "loose@example.com is attached unsubscribed: the member is unsubscribed at every other address "
            "(re-subscribing needs the person's consent)",
            outcome.notes,
        )


class ContactsHeldElsewhereTests(ImportTestCase):
    """Neither a new member nor an update takes an address or number that another member, or nobody, holds."""

    def setUp(self):
        super().setUp()
        self.grace = self.member("Grace", "Hopper", "grace@example.com")
        self.grace_label = f"Grace Hopper (member {self.grace.pk})"
        self.nina = {"First_Name": "Nina", "Last_Name": "New"}

    def test_a_new_member_takes_an_unlinked_secondary_unverified(self):
        loose = ContactEmail.objects.create(
            member=None, email_address="loose@example.com", verified=True, subscribe=False
        )
        cells_row = row("nina@example.com", Secondary_Email="loose@example.com", Secondary_Verified="TRUE", **self.nina)

        (outcome,) = self.apply([cells_row])

        loose.refresh_from_db()
        self.assertEqual(
            (loose.member, loose.email_type, loose.verified, loose.subscribe),
            (outcome.member, "secondary", False, False),
        )
        self.assertIn(
            "Attaches loose@example.com (a contact email with no member) as the secondary email (unverified, not "
            "subscribed)",
            outcome.changes,
        )

    def test_a_new_member_never_takes_a_contact_of_another_member(self):
        self.email(self.grace, "grace.work@example.com")
        self.phone(self.grace, "2095550101")
        cells_row = row(
            "nina@example.com", Secondary_Email="grace.work@example.com", Phone_Number="2095550101", **self.nina
        )

        (outcome,) = self.apply([cells_row])

        self.assertEqual(outcome.outcome, "created")
        self.assertEqual(
            outcome.notes,
            [
                f"Secondary Email grace.work@example.com is already used by {self.grace_label}; not added",
                f"Phone Number +12095550101 is already used by {self.grace_label}; not added",
            ],
        )
        self.assertEqual(ContactEmail.objects.get(email_address="grace.work@example.com").member, self.grace)
        self.assertEqual(ContactPhone.objects.get(phone_number="2095550101").member, self.grace)

    def test_a_new_member_never_takes_an_ambiguous_secondary_or_an_unlinked_number(self):
        ContactEmail.objects.create(member=None, email_address="dup@example.com")
        ContactEmail.objects.create(member=None, email_address="DUP@example.com")
        ContactPhone.objects.create(member=None, phone_number="2095550101", region="1-US")
        cells_row = row("nina@example.com", Secondary_Email="dup@example.com", Phone_Number="2095550101", **self.nina)

        (outcome,) = self.apply([cells_row])

        self.assertEqual(
            outcome.notes,
            [
                "Secondary Email dup@example.com is already used by 2 contact emails that differ only in letter case; "
                "not added",
                "Phone Number +12095550101 is already used by a contact phone that is not linked to any member; not "
                "added",
            ],
        )
        self.assertEqual(
            list(outcome.member.contact_emails.values_list("email_address", flat=True)), ["nina@example.com"]
        )
        self.assertFalse(outcome.member.contact_phones.exists())

    def test_an_update_never_takes_an_ambiguous_secondary_or_an_unlinked_number(self):
        old = self.email(self.ada, "ada.old@example.com")
        ContactEmail.objects.create(member=None, email_address="dup@example.com")
        self.email(self.grace, "DUP@example.com", "other")
        unlinked = ContactPhone.objects.create(member=None, phone_number="2095550101", region="1-US")
        cells_row = row("ada@example.com", Secondary_Email="dup@example.com", Phone_Number="2095550101")

        analysis = self.analyse_one(cells_row)
        (outcome,) = self.apply([cells_row])

        self.assertEqual((analysis.risky, outcome.outcome), ({}, "no_change"))
        self.assertEqual(
            outcome.notes,
            [
                "Secondary Email dup@example.com matches 2 contact emails that differ only in letter case; not added "
                "(merge them under Contact Emails)",
                "Phone Number +12095550101 is a contact with no member; not added (link it under Contact Emails or "
                "Phones)",
            ],
        )
        old.refresh_from_db()
        unlinked.refresh_from_db()
        self.assertEqual((old.email_type, unlinked.member), ("secondary", None))
