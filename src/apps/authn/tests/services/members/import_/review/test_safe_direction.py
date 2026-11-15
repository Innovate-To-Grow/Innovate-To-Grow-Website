from django.core import mail

from apps.authn.models import ContactEmail, ContactPhone
from apps.authn.tests.services.members.import_.helpers import ImportTestCase, row


class SafeDirectionTests(ImportTestCase):
    """TRUE verifies and FALSE unsubscribes a contact the row names, without a tick, when the member owns it."""

    def setUp(self):
        super().setUp()
        self.primary = self.ada.contact_emails.get()
        self.work = self.email(self.ada, "ada.work@example.com", verified=False, subscribe=True)
        self.mobile = self.phone(self.ada, "2095550101", verified=False, subscribe=True)
        self.named = {"Secondary_Email": "ada.work@example.com", "Phone_Number": "2095550101"}

    def test_verified_true_verifies_an_address_only_with_its_tick_and_never_a_phone_number(self):
        """A verified address is a sign-in factor, so marking one verified is its own tick (R9), off by default. A phone
        number is never marked verified, ticked or not: the Phone Verified column is ignored."""
        cells_row = row("ada@example.com", Secondary_Verified="TRUE", Phone_Verified="TRUE", **self.named)

        analysis = self.analyse_one(cells_row)
        (unticked,) = self.apply([cells_row])

        items = [item["id"] for item in analysis.risky[str(self.ada.pk)]]
        self.assertEqual((analysis.status, items), ("no_change", [f"R9:{self.work.pk}"]))
        self.assertEqual(unticked.outcome, "no_change")
        self.work.refresh_from_db()
        self.mobile.refresh_from_db()
        self.assertEqual((self.work.verified, self.mobile.verified), (False, False))

        # A forged tick for the number reaches the planner here (the review refuses it on save): still ignored.
        (ticked,) = self.apply([cells_row], {2: ("update", [f"R9:{self.work.pk}", f"R9:{self.mobile.pk}"])})

        self.assertEqual(ticked.outcome, "updated")
        self.work.refresh_from_db()
        self.mobile.refresh_from_db()
        self.assertEqual((self.work.verified, self.mobile.verified), (True, False))
        self.assertEqual(ticked.changes, ["Marks ada.work@example.com verified"])
        self.assertEqual(ticked.listed["verified"], ["ada.work@example.com"])

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

    def test_a_new_member_trusts_the_sheet_email_flags_but_never_phone_verified(self):
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
            [("2095550155", False, True)],
        )
        self.assertIn("Phone +12095550155 (unverified, subscribed)", outcome.changes)
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
