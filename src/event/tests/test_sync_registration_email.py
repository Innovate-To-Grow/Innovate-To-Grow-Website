from unittest.mock import patch

from django.db import IntegrityError
from django.test import TestCase

from authn.models import ContactEmail
from event.services.sync_registration_email import sync_secondary_email_to_account
from event.tests.helpers import make_member


class SyncSecondaryEmailToAccountTest(TestCase):
    def setUp(self):
        self.member = make_member(email="primary@example.com")

    def test_creates_secondary_contact_email(self):
        sync_secondary_email_to_account(self.member, "new@example.com")
        contact = ContactEmail.objects.get(email_address="new@example.com")
        self.assertEqual(contact.member, self.member)
        self.assertEqual(contact.email_type, "secondary")
        self.assertFalse(contact.verified)

    def test_skips_when_email_belongs_to_same_member(self):
        ContactEmail.objects.create(member=self.member, email_address="existing@example.com", email_type="secondary")
        sync_secondary_email_to_account(self.member, "existing@example.com")
        self.assertEqual(ContactEmail.objects.filter(email_address="existing@example.com").count(), 1)

    def test_skips_when_email_belongs_to_other_member(self):
        other = make_member(email="other@example.com")
        ContactEmail.objects.create(member=other, email_address="taken@example.com", email_type="secondary")
        sync_secondary_email_to_account(self.member, "taken@example.com")
        contact = ContactEmail.objects.get(email_address="taken@example.com")
        self.assertEqual(contact.member, other)

    def test_skips_empty_email(self):
        sync_secondary_email_to_account(self.member, "")
        self.assertEqual(ContactEmail.objects.filter(member=self.member).count(), 1)  # only primary

    def test_skips_blank_email(self):
        sync_secondary_email_to_account(self.member, "   ")
        self.assertEqual(ContactEmail.objects.filter(member=self.member).count(), 1)

    def test_handles_concurrent_integrity_error(self):
        with patch.object(ContactEmail.objects, "create", side_effect=IntegrityError):
            sync_secondary_email_to_account(self.member, "race@example.com")
        # Should not raise — swallowed silently

    def test_case_insensitive_lookup(self):
        ContactEmail.objects.create(member=self.member, email_address="Mixed@Example.com", email_type="secondary")
        sync_secondary_email_to_account(self.member, "mixed@example.com")
        self.assertEqual(ContactEmail.objects.filter(email_address__iexact="mixed@example.com").count(), 1)
