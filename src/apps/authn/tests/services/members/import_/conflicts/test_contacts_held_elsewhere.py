from apps.authn.models import ContactEmail, ContactPhone
from apps.authn.tests.services.members.import_.helpers import ImportTestCase, row


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
