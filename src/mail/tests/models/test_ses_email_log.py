"""Tests for mail app models."""

from django.test import TestCase

from mail.models import SESAccount, SESEmailLog

FAKE_SERVICE_JSON = '{"type":"service_account","project_id":"test","private_key":"key","client_email":"sa@test.iam.gserviceaccount.com"}'


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
