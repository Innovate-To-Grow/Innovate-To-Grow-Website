import io
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError
from django.test import TestCase

from apps.authn.management.commands.ensure_default_admin import Command
from apps.authn.models import ContactEmail


class EnsureDefaultAdminCommandTests(TestCase):
    def test_concurrent_compliant_winner_is_treated_as_idempotent(self):
        Member = get_user_model()
        winner = Member.objects.create_user(
            password="winner-password",
            first_name="Winner",
            last_name="Admin",
            is_active=True,
            is_staff=True,
        )
        winner_contact = ContactEmail.objects.create(
            member=winner,
            email_address="race@example.com",
            email_type="primary",
            verified=True,
            subscribe=False,
        )
        out = io.StringIO()

        # Simulate the first lookup's snapshot missing a row which is visible
        # by the time get_or_create handles the competing insert.
        with (
            patch.object(Command, "_find_contact_for_update", side_effect=[None, winner_contact]),
            patch.dict("os.environ", {"DJANGO_SUPERUSER_PASSWORD": "loser-password"}),
        ):
            call_command(
                Command(),
                yes=True,
                email="race@example.com",
                stdout=out,
            )

        self.assertEqual(Member.objects.count(), 1)
        self.assertEqual(ContactEmail.objects.filter(email_address="race@example.com").count(), 1)
        winner.refresh_from_db()
        winner_contact.refresh_from_db()
        self.assertTrue(winner.check_password("winner-password"))
        self.assertFalse(winner_contact.subscribe)
        self.assertIn("already exists; left unchanged", out.getvalue())

    def test_concurrent_non_admin_winner_is_rejected_unchanged(self):
        Member = get_user_model()
        winner = Member.objects.create_user(
            password="winner-password",
            first_name="Ordinary",
            last_name="Member",
            is_active=True,
            is_staff=False,
        )
        winner_contact = ContactEmail.objects.create(
            member=winner,
            email_address="race@example.com",
            email_type="primary",
            verified=True,
            subscribe=False,
        )

        with (
            patch.object(Command, "_find_contact_for_update", side_effect=[None, winner_contact]),
            patch.dict("os.environ", {"DJANGO_SUPERUSER_PASSWORD": "loser-password"}),
            self.assertRaisesMessage(CommandError, "not an active Admin"),
        ):
            call_command(
                Command(),
                yes=True,
                email="race@example.com",
                stdout=io.StringIO(),
            )

        self.assertEqual(Member.objects.count(), 1)
        winner.refresh_from_db()
        winner_contact.refresh_from_db()
        self.assertTrue(winner.check_password("winner-password"))
        self.assertFalse(winner.is_staff)
        self.assertFalse(winner.is_superuser)
        self.assertTrue(winner_contact.verified)
        self.assertFalse(winner_contact.subscribe)

    def test_unrelated_integrity_error_is_not_treated_as_a_concurrent_winner(self):
        with (
            patch.object(ContactEmail.objects, "get_or_create", side_effect=IntegrityError("unrelated constraint")),
            patch.dict("os.environ", {"DJANGO_SUPERUSER_PASSWORD": "safe-demo-password"}),
            self.assertRaisesMessage(IntegrityError, "unrelated constraint"),
        ):
            call_command(
                Command(),
                yes=True,
                email="new@example.com",
                stdout=io.StringIO(),
            )

        self.assertEqual(get_user_model().objects.count(), 0)

    def test_existing_admin_does_not_require_password_secret(self):
        Member = get_user_model()
        member = Member.objects.create_user(
            password="existing-password",
            first_name="Existing",
            last_name="Admin",
            is_active=True,
            is_staff=True,
        )
        ContactEmail.objects.create(
            member=member,
            email_address="existing-admin@example.com",
            email_type="primary",
            verified=True,
            subscribe=True,
        )

        with patch.dict("os.environ", {}, clear=True):
            call_command(
                Command(),
                yes=True,
                email="existing-admin@example.com",
                stdout=io.StringIO(),
            )

        member.refresh_from_db()
        self.assertTrue(member.check_password("existing-password"))

    def test_existing_admin_with_unverified_contact_is_rejected_unchanged(self):
        Member = get_user_model()
        member = Member.objects.create_user(
            password="existing-password",
            first_name="Existing",
            last_name="Admin",
            is_active=True,
            is_staff=True,
        )
        contact = ContactEmail.objects.create(
            member=member,
            email_address="unverified-admin@example.com",
            email_type="primary",
            verified=False,
            subscribe=False,
        )

        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesMessage(CommandError, "contact is not verified"):
                call_command(
                    Command(),
                    yes=True,
                    email="unverified-admin@example.com",
                    stdout=io.StringIO(),
                )

        member.refresh_from_db()
        contact.refresh_from_db()
        self.assertEqual(member.first_name, "Existing")
        self.assertEqual(member.last_name, "Admin")
        self.assertTrue(member.is_active)
        self.assertTrue(member.is_staff)
        self.assertTrue(member.is_superuser)
        self.assertTrue(member.check_password("existing-password"))
        self.assertFalse(contact.verified)
        self.assertFalse(contact.subscribe)
