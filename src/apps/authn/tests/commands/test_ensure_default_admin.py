import io
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.authn.management.commands.ensure_default_admin import Command
from apps.authn.models import ContactEmail


class EnsureDefaultAdminCommandTests(TestCase):
    def test_requires_explicit_confirmation(self):
        with self.assertRaisesMessage(CommandError, "without --yes"):
            call_command(Command(), email="demo-admin@example.com")

    def test_requires_password_env(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesMessage(CommandError, "DJANGO_SUPERUSER_PASSWORD must be set"):
                call_command(Command(), yes=True, email="demo-admin@example.com")

    def test_creates_default_admin_once_and_leaves_it_unchanged(self):
        out = io.StringIO()

        with patch.dict("os.environ", {"DJANGO_SUPERUSER_PASSWORD": "safe-demo-password"}):
            call_command(
                Command(),
                yes=True,
                email="demo-admin@example.com",
                first_name="Demo",
                last_name="Admin",
                stdout=out,
            )

        with patch.dict("os.environ", {"DJANGO_SUPERUSER_PASSWORD": "replacement-password"}):
            call_command(
                Command(),
                yes=True,
                email="demo-admin@example.com",
                first_name="Replacement",
                last_name="Name",
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
        self.assertIn("already exists; left unchanged", out.getvalue())

    def test_existing_member_is_never_promoted_or_reset(self):
        Member = get_user_model()
        member = Member.objects.create_user(
            password="old-password",
            first_name="Old",
            last_name="User",
            is_active=False,
            is_staff=False,
        )
        ContactEmail.objects.create(
            member=member,
            email_address="existing@example.com",
            email_type="primary",
            verified=False,
            subscribe=False,
        )

        with patch.dict("os.environ", {"DJANGO_SUPERUSER_PASSWORD": "new-password"}):
            with self.assertRaisesMessage(CommandError, "not an active Admin"):
                call_command(
                    Command(),
                    yes=True,
                    email="existing@example.com",
                    first_name="Default",
                    last_name="Admin",
                    stdout=io.StringIO(),
                )

        member.refresh_from_db()
        contact = ContactEmail.objects.get(email_address="existing@example.com")
        self.assertEqual(contact.member, member)
        self.assertEqual(member.first_name, "Old")
        self.assertEqual(member.last_name, "User")
        self.assertFalse(member.is_active)
        self.assertFalse(member.is_staff)
        self.assertFalse(member.is_superuser)
        self.assertTrue(member.check_password("old-password"))
        self.assertFalse(contact.verified)
        self.assertFalse(contact.subscribe)

    def test_unowned_contact_is_claimed_by_new_admin(self):
        contact = ContactEmail.objects.create(
            member=None,
            email_address="subscribed@example.com",
            email_type="other",
            verified=False,
            subscribe=False,
        )

        with patch.dict("os.environ", {"DJANGO_SUPERUSER_PASSWORD": "safe-demo-password"}):
            call_command(
                Command(),
                yes=True,
                email="subscribed@example.com",
                first_name="Default",
                last_name="Admin",
                stdout=io.StringIO(),
            )

        contact.refresh_from_db()
        member = contact.member
        self.assertEqual(ContactEmail.objects.filter(email_address="subscribed@example.com").count(), 1)
        self.assertTrue(member.is_active)
        self.assertTrue(member.is_staff)
        self.assertTrue(member.is_superuser)
        self.assertTrue(member.check_password("safe-demo-password"))
        self.assertEqual(contact.email_type, "primary")
        self.assertTrue(contact.verified)
        self.assertFalse(contact.subscribe)

    def _existing(self, email, **flags):
        member = get_user_model().objects.create_user(
            password="existing-password", first_name="Existing", last_name="Admin", **flags
        )
        ContactEmail.objects.create(member=member, email_address=email, email_type="primary", verified=True)
        return member

    def test_an_active_admin_is_accepted_whatever_its_superuser_column(self):
        """The command decides on ``is_staff``: a row whose ``is_superuser`` mirror is stale still boots."""
        member = self._existing("stale-admin@example.com", is_active=True, is_staff=True)
        get_user_model().objects.filter(pk=member.pk).update(is_superuser=False)
        out = io.StringIO()

        with patch.dict("os.environ", {}, clear=True):
            call_command(Command(), yes=True, email="stale-admin@example.com", stdout=out)

        self.assertIn("already exists; left unchanged", out.getvalue())

    def test_an_inactive_admin_is_refused(self):
        self._existing("inactive-admin@example.com", is_active=False, is_staff=True)

        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesMessage(CommandError, "not an active Admin"):
                call_command(Command(), yes=True, email="inactive-admin@example.com", stdout=io.StringIO())
