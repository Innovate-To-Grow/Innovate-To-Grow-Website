from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase

from authn.models import ContactEmail

Member = get_user_model()


class CreateSuperuserCommandTests(TestCase):
    def test_noninteractive_requires_first_and_last_name(self):
        with self.assertRaisesMessage(
            CommandError,
            "--email, --password, --first-name, and --last-name are required in non-interactive mode.",
        ):
            call_command(
                "createsuperuser",
                "--noinput",
                "--email=admin@example.com",
                "--password=StrongPass123!",
            )

    def test_noninteractive_creates_superuser_with_names(self):
        stdout = StringIO()

        call_command(
            "createsuperuser",
            "--noinput",
            "--email=admin@example.com",
            "--password=StrongPass123!",
            "--first-name=Admin",
            "--last-name=User",
            stdout=stdout,
        )

        member = ContactEmail.objects.get(email_address="admin@example.com").member
        self.assertTrue(member.is_superuser)
        self.assertEqual(member.first_name, "Admin")
        self.assertEqual(member.last_name, "User")


class MemberManagerCreateSuperuserTests(TestCase):
    def test_create_superuser_requires_first_name(self):
        with self.assertRaisesMessage(ValueError, "Superuser first name is required."):
            Member.objects.create_superuser(password="StrongPass123!", last_name="User")

    def test_create_superuser_requires_last_name(self):
        with self.assertRaisesMessage(ValueError, "Superuser last name is required."):
            Member.objects.create_superuser(password="StrongPass123!", first_name="Admin")
