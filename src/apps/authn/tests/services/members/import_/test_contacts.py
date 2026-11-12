"""The guarded contact writes of an apply: a record that is no longer what the review saw stops the import.

Each refused write raises ``ContactWriteError``, which the apply turns into ``RowWriteError`` and a full rollback. The
writes go through the account page's own services where they exist, so their guards hold, and none of them sends mail.
"""

from django.core import mail
from django.db import transaction

from apps.authn.models import ContactEmail, ContactPhone, Member
from apps.authn.services.members.import_ import contacts
from apps.authn.services.members.import_.contacts import ContactWriteError, phone_parts, valid_new_address
from apps.authn.tests.services.members.import_.helpers import ImportTestCase

LAST_CONTACT = "You can't remove your only verified recovery method. Add and verify another email or phone first."


class ContactWriteGuardTests(ImportTestCase):
    def setUp(self):
        super().setUp()
        self.primary = self.ada.contact_emails.get()
        self.grace = self.member("Grace", "Hopper", "grace@example.com")

    def refused(self, message, write, *args):
        with self.assertRaisesMessage(ContactWriteError, message):
            with transaction.atomic():
                write(*args)

    def test_flags_of_a_contact_the_member_does_not_own(self):
        theirs = self.grace.contact_emails.get()
        phone = self.phone(self.grace, "2095550101")

        self.refused(
            "a contact email the review showed no longer belongs to this member",
            contacts.set_email_flags,
            self.ada,
            str(theirs.pk),
            {"verified": False},
        )
        self.refused(
            "a phone number the review showed no longer belongs to this member",
            contacts.set_phone_flags,
            self.ada,
            str(phone.pk),
            {"subscribe": True},
        )

        theirs.refresh_from_db()
        phone.refresh_from_db()
        self.assertEqual((theirs.verified, phone.verified, phone.subscribe), (True, False, False))

    def test_flags_of_an_owned_contact(self):
        phone = self.phone(self.ada, "2095550101")

        contacts.set_email_flags(self.ada, str(self.primary.pk), {"subscribe": False})
        # Subscribed is the only flag an import may write on a number (test_phone_verified.GuardedWriteTests).
        contacts.set_phone_flags(self.ada, str(phone.pk), {"subscribe": True})

        self.primary.refresh_from_db()
        phone.refresh_from_db()
        self.assertEqual((self.primary.subscribe, phone.verified, phone.subscribe), (False, False, True))

    def test_an_unverified_address_is_never_made_primary(self):
        work = self.email(self.ada, "ada.work@example.com", verified=False)

        self.refused("Verify this email before setting it as primary.", contacts.promote_email, self.ada, str(work.pk))

        work.refresh_from_db()
        self.assertEqual(work.email_type, "secondary")

    def test_an_unlinked_address_taken_after_the_review(self):
        taken = ContactEmail.objects.create(member=self.grace, email_address="loose@example.com", email_type="other")
        data = {"type": "secondary", "verified": False, "subscribe": True}

        self.refused(
            "the contact email with no member was taken or removed after the review",
            contacts.claim_email,
            self.ada,
            str(taken.pk),
            data,
        )

        taken.refresh_from_db()
        self.assertEqual(taken.member, self.grace)

    def test_a_number_taken_after_the_review(self):
        self.phone(self.grace, "2095550101")

        self.refused(
            "This phone number is already in use.",
            contacts.add_phone,
            self.ada,
            {"number": "2095550101", "region": "1-US", "subscribe": False},
        )

        self.assertFalse(self.ada.contact_phones.exists())

    def test_the_last_verified_sign_in_contact_is_never_deleted(self):
        pat = Member.objects.create_user(password="StrongPass123!", first_name="Pat", last_name="Phone")
        only = self.phone(pat, "2095550111", verified=True)

        self.refused(LAST_CONTACT, contacts.delete_email, self.ada, str(self.primary.pk))
        self.refused(LAST_CONTACT, contacts.delete_phone, pat, str(only.pk))

        self.assertTrue(ContactEmail.objects.filter(pk=self.primary.pk).exists())
        self.assertTrue(ContactPhone.objects.filter(pk=only.pk).exists())

    def test_a_new_address_demotes_the_listed_secondaries_and_sends_no_mail(self):
        old = self.email(self.ada, "ada.old@example.com")
        data = {"address": "ada.new@example.com", "type": "secondary", "verified": False, "subscribe": True}

        contacts.add_email(self.ada, {**data, "demote": [str(old.pk)]})

        old.refresh_from_db()
        self.assertEqual(old.email_type, "other")
        new = ContactEmail.objects.get(email_address="ada.new@example.com")
        self.assertEqual((new.member, new.email_type, new.verified), (self.ada, "secondary", False))
        self.assertEqual(mail.outbox, [])


class ContactCheckTests(ImportTestCase):
    def test_a_new_address_must_be_a_valid_email_that_fits(self):
        self.assertTrue(valid_new_address("ada@example.com"))
        self.assertFalse(valid_new_address("ada@"))
        self.assertFalse(valid_new_address(f"{'a' * 250}@example.com"))

    def test_phone_parts(self):
        self.assertEqual(phone_parts("+12095550101"), ("2095550101", "1-US"))
        self.assertEqual(phone_parts(None), ("", ""))
        self.assertEqual(phone_parts(""), ("", ""))
