import io
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.authn.models import ContactEmail


class EnsureDefaultAdminCommandTests(TestCase):
    def test_requires_explicit_confirmation(self):
        with self.assertRaisesMessage(CommandError, "without --yes"):
            call_command("ensure_default_admin", email="demo-admin@example.com")

    def test_requires_password_env(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesMessage(CommandError, "DJANGO_SUPERUSER_PASSWORD must be set"):
                call_command("ensure_default_admin", "--yes", email="demo-admin@example.com")

    def test_creates_default_admin_idempotently(self):
        out = io.StringIO()

        with patch.dict("os.environ", {"DJANGO_SUPERUSER_PASSWORD": "safe-demo-password"}):
            call_command(
                "ensure_default_admin",
                "--yes",
                email="demo-admin@example.com",
                first_name="Demo",
                last_name="Admin",
                stdout=out,
            )
            call_command(
                "ensure_default_admin",
                "--yes",
                email="demo-admin@example.com",
                first_name="Demo",
                last_name="Admin",
                stdout=out,
            )

        Member = get_user_model()
        contact = ContactEmail.objects.get(email_address="demo-admin@example.com")
        member = contact.member

        self.assertEqual(Member.objects.count(), 1)
        self.assertEqual(ContactEmail.objects.filter(email_address="demo-admin@example.com").count(), 1)
        self.assertEqual(member.first_name, "Demo")
        self.assertEqual(member.last_name, "Admin")
        self.assertTrue(member.is_active)
        self.assertTrue(member.is_staff)
        self.assertTrue(member.is_superuser)
        self.assertTrue(member.check_password("safe-demo-password"))
        self.assertEqual(contact.email_type, "primary")
        self.assertTrue(contact.verified)
        self.assertIn("Default admin created", out.getvalue())
        self.assertIn("Default admin updated", out.getvalue())

    def test_promotes_existing_member_for_email(self):
        Member = get_user_model()
        member = Member.objects.create_user(
            password="old-password",
            first_name="Old",
            last_name="User",
            is_active=False,
            is_staff=False,
            is_superuser=False,
        )
        ContactEmail.objects.create(
            member=member,
            email_address="existing@example.com",
            email_type="primary",
            verified=False,
            subscribe=False,
        )

        with patch.dict("os.environ", {"DJANGO_SUPERUSER_PASSWORD": "new-password"}):
            call_command(
                "ensure_default_admin",
                "--yes",
                email="existing@example.com",
                first_name="Default",
                last_name="Admin",
                stdout=io.StringIO(),
            )

        member.refresh_from_db()
        contact = ContactEmail.objects.get(email_address="existing@example.com")
        self.assertEqual(contact.member, member)
        self.assertEqual(member.first_name, "Default")
        self.assertEqual(member.last_name, "Admin")
        self.assertTrue(member.is_active)
        self.assertTrue(member.is_staff)
        self.assertTrue(member.is_superuser)
        self.assertTrue(member.check_password("new-password"))
        self.assertTrue(contact.verified)
        self.assertTrue(contact.subscribe)
