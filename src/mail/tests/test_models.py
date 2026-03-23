"""Tests for mail app models."""

import importlib

from django.apps import apps
from django.test import TestCase

from mail.models import EmailLog, GoogleAccount, SESAccount, SESEmailLog

FAKE_SERVICE_JSON = '{"type":"service_account","project_id":"test","private_key":"key","client_email":"sa@test.iam.gserviceaccount.com"}'


class GoogleAccountModelTest(TestCase):
    """Tests for GoogleAccount model."""

    def test_create_account(self):
        account = GoogleAccount.objects.create(
            email="test@example.com",
            display_name="Test",
            service_account_json=FAKE_SERVICE_JSON,
            is_active=True,
        )
        self.assertEqual(str(account), "Test")
        self.assertTrue(account.is_active)
        self.assertIsNotNone(account.id)

    def test_singleton_active_pattern(self):
        """Only one account should be active at a time."""
        a1 = GoogleAccount.objects.create(
            email="a1@example.com",
            service_account_json=FAKE_SERVICE_JSON,
            is_active=True,
        )
        a2 = GoogleAccount.objects.create(
            email="a2@example.com",
            service_account_json=FAKE_SERVICE_JSON,
            is_active=True,
        )
        a1.refresh_from_db()
        self.assertFalse(a1.is_active)
        self.assertTrue(a2.is_active)

    def test_get_active(self):
        GoogleAccount.objects.create(
            email="inactive@example.com",
            service_account_json=FAKE_SERVICE_JSON,
            is_active=False,
        )
        active = GoogleAccount.objects.create(
            email="active@example.com",
            service_account_json=FAKE_SERVICE_JSON,
            is_active=True,
        )
        self.assertEqual(GoogleAccount.get_active(), active)

    def test_get_active_returns_none(self):
        self.assertIsNone(GoogleAccount.get_active())

    def test_mark_used(self):
        account = GoogleAccount.objects.create(
            email="test@example.com",
            service_account_json=FAKE_SERVICE_JSON,
        )
        account.mark_used(error="test error")
        account.refresh_from_db()
        self.assertIsNotNone(account.last_used_at)
        self.assertEqual(account.last_error, "test error")

    def test_mark_used_clears_error(self):
        account = GoogleAccount.objects.create(
            email="test@example.com",
            service_account_json=FAKE_SERVICE_JSON,
            last_error="old error",
        )
        account.mark_used()
        account.refresh_from_db()
        self.assertEqual(account.last_error, "")

    def test_soft_delete(self):
        account = GoogleAccount.objects.create(
            email="test@example.com",
            service_account_json=FAKE_SERVICE_JSON,
        )
        account.delete()
        self.assertEqual(GoogleAccount.objects.count(), 0)
        self.assertEqual(GoogleAccount.all_objects.count(), 1)

    def test_get_active_excludes_deleted(self):
        account = GoogleAccount.objects.create(
            email="test@example.com",
            service_account_json=FAKE_SERVICE_JSON,
            is_active=True,
        )
        account.delete()
        self.assertIsNone(GoogleAccount.get_active())

    def test_str_inactive(self):
        account = GoogleAccount(email="test@example.com", is_active=False)
        self.assertEqual(str(account), "test@example.com [Inactive]")

    def test_str_with_display_name(self):
        account = GoogleAccount(email="test@example.com", display_name="ITG", is_active=True)
        self.assertEqual(str(account), "ITG")


class EmailLogModelTest(TestCase):
    """Tests for EmailLog model."""

    # noinspection PyPep8Naming
    def setUp(self):
        self.account = GoogleAccount.objects.create(
            email="test@example.com",
            service_account_json=FAKE_SERVICE_JSON,
        )

    def test_create_log(self):
        log = EmailLog.objects.create(
            account=self.account,
            action=EmailLog.Action.SEND,
            status=EmailLog.Status.SUCCESS,
            subject="Test Subject",
            recipients="user@example.com",
        )
        self.assertEqual(str(log), "Send - Test Subject")

    def test_ordering(self):
        """Logs should be ordered by newest first."""
        log1 = EmailLog.objects.create(
            account=self.account,
            action=EmailLog.Action.SEND,
            status=EmailLog.Status.SUCCESS,
            subject="First",
        )
        log2 = EmailLog.objects.create(
            account=self.account,
            action=EmailLog.Action.READ,
            status=EmailLog.Status.SUCCESS,
            subject="Second",
        )
        logs = list(EmailLog.objects.all())
        self.assertEqual(logs[0], log2)
        self.assertEqual(logs[1], log1)

    def test_str_no_subject(self):
        log = EmailLog(action=EmailLog.Action.READ, status=EmailLog.Status.SUCCESS)
        self.assertEqual(str(log), "Read - (no subject)")

    def test_account_cascade_set_null(self):
        log = EmailLog.objects.create(
            account=self.account,
            action=EmailLog.Action.SEND,
            status=EmailLog.Status.SUCCESS,
        )
        self.account.hard_delete()
        log.refresh_from_db()
        self.assertIsNone(log.account)


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


class SESEmailLogModelTest(TestCase):
    """Tests for SESEmailLog model."""

    # noinspection PyPep8Naming
    def setUp(self):
        SESAccount.all_objects.all().hard_delete()
        self.account = SESAccount.objects.create(display_name="SES Sender")

    def test_create_log(self):
        log = SESEmailLog.objects.create(
            account=self.account,
            status=SESEmailLog.Status.SUCCESS,
            subject="SES Subject",
            recipients="user@example.com",
            ses_message_id="ses-123",
        )
        self.assertEqual(str(log), "Send - SES Subject")

    def test_ordering(self):
        first = SESEmailLog.objects.create(
            account=self.account,
            status=SESEmailLog.Status.SUCCESS,
            subject="First",
        )
        second = SESEmailLog.objects.create(
            account=self.account,
            status=SESEmailLog.Status.FAILED,
            subject="Second",
        )
        logs = list(SESEmailLog.objects.all())
        self.assertEqual(logs[0], second)
        self.assertEqual(logs[1], first)


class SESLogBackfillMigrationTest(TestCase):
    # noinspection PyPep8Naming
    def setUp(self):
        SESAccount.all_objects.all().hard_delete()
        self.account = SESAccount.objects.create(display_name="SES Sender")

    def test_backfill_creates_generic_email_logs(self):
        ses_log = SESEmailLog.objects.create(
            account=self.account,
            status=SESEmailLog.Status.SUCCESS,
            subject="Backfill Subject",
            recipients="user@example.com",
            ses_message_id="ses-123",
        )

        migration = importlib.import_module("mail.migrations.0003_backfill_ses_logs_into_email_logs")
        migration.backfill_ses_logs_into_email_logs(apps, None)
        migration.backfill_ses_logs_into_email_logs(apps, None)

        email_log = EmailLog.objects.get(gmail_message_id="ses-123")
        self.assertEqual(EmailLog.objects.filter(gmail_message_id="ses-123").count(), 1)
        self.assertEqual(email_log.status, EmailLog.Status.SUCCESS)
        self.assertEqual(email_log.subject, ses_log.subject)
        self.assertEqual(email_log.recipients, ses_log.recipients)
