"""Tests for mail app models."""

from django.test import TestCase

from mail.models import EmailLog, GoogleAccount

FAKE_SERVICE_JSON = '{"type":"service_account","project_id":"test","private_key":"key","client_email":"sa@test.iam.gserviceaccount.com"}'


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
