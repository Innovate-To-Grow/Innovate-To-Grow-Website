"""Tests for mail app models."""

import importlib

from django.apps import apps
from django.test import TestCase

from mail.models import EmailLog, SESAccount, SESEmailLog

FAKE_SERVICE_JSON = '{"type":"service_account","project_id":"test","private_key":"key","client_email":"sa@test.iam.gserviceaccount.com"}'


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
