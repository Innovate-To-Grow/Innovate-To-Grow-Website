"""Tests for mail app models."""

from django.test import TestCase

from mail.models import SESAccount

FAKE_SERVICE_JSON = '{"type":"service_account","project_id":"test","private_key":"key","client_email":"sa@test.iam.gserviceaccount.com"}'


class SESAccountModelTest(TestCase):
    """Tests for SESAccount model."""

    # noinspection PyMethodMayBeStatic,PyPep8Naming
    def setUp(self):
        SESAccount.all_objects.all().hard_delete()

    def test_create_account(self):
        account = SESAccount.objects.create(
            display_name="Innovate to Grow",
            is_active=True,
        )
        self.assertEqual(str(account), "Innovate to Grow")
        self.assertEqual(account.email, "i2g@g.ucmerced.edu")
        self.assertTrue(account.is_active)

    def test_fixed_sender_email(self):
        account = SESAccount.objects.create(
            email="other@example.com",
            display_name="Custom Name",
        )
        self.assertEqual(account.email, "i2g@g.ucmerced.edu")

    def test_single_active_sender(self):
        first = SESAccount.objects.create(display_name="First", is_active=True)
        second = SESAccount.objects.create(display_name="Second", is_active=True)
        first.refresh_from_db()
        self.assertFalse(first.is_active)
        self.assertTrue(second.is_active)

    def test_get_active(self):
        SESAccount.objects.create(display_name="Inactive", is_active=False)
        active = SESAccount.objects.create(display_name="Active", is_active=True)
        self.assertEqual(SESAccount.get_active(), active)

    def test_mark_used(self):
        account = SESAccount.objects.create(display_name="Test Sender")
        account.mark_used(error="ses failed")
        account.refresh_from_db()
        self.assertIsNotNone(account.last_used_at)
        self.assertEqual(account.last_error, "ses failed")

    def test_default_data_migration_creates_sender(self):
        SESAccount.all_objects.all().hard_delete()
        # Simulate the post-migrate state created by the migration.
        SESAccount.objects.create()
        account = SESAccount.get_active()
        self.assertIsNotNone(account)
        self.assertEqual(account.email, "i2g@g.ucmerced.edu")
