"""Tests for the send_email() convenience function."""

from unittest.mock import patch

from django.test import TestCase

from mail.models import EmailLog, GoogleAccount
from mail.services import send_email
from mail.services.gmail import GmailServiceError

FAKE_SERVICE_JSON = '{"type":"service_account","project_id":"test","private_key":"key","client_email":"sa@test.iam.gserviceaccount.com"}'


class SendEmailTest(TestCase):
    """Tests for the send_email() convenience function."""

    # noinspection PyPep8Naming
    def setUp(self):
        self.account = GoogleAccount.objects.create(
            email="i2g@g.ucmerced.edu",
            display_name="ITG",
            service_account_json=FAKE_SERVICE_JSON,
            is_active=True,
        )

    @patch("mail.services.gmail.GmailService.send_message")
    def test_send_email_success(self, mock_send):
        mock_send.return_value = {"id": "msg123", "thread_id": "t123"}

        result = send_email(
            to="student@ucmerced.edu",
            subject="Your OTP Code",
            body_html="<p>Code: <b>123456</b></p>",
        )

        self.assertEqual(result["id"], "msg123")
        mock_send.assert_called_once_with(
            to="student@ucmerced.edu",
            subject="Your OTP Code",
            body_html="<p>Code: <b>123456</b></p>",
            cc="",
            bcc="",
            attachments=None,
        )

        # Verify EmailLog created
        log = EmailLog.objects.first()
        self.assertEqual(log.action, EmailLog.Action.SEND)
        self.assertEqual(log.status, EmailLog.Status.SUCCESS)
        self.assertEqual(log.recipients, "student@ucmerced.edu")
        self.assertEqual(log.subject, "Your OTP Code")
        self.assertEqual(log.gmail_message_id, "msg123")

    @patch("mail.services.gmail.GmailService.send_message")
    def test_send_email_with_cc_bcc(self, mock_send):
        mock_send.return_value = {"id": "msg456", "thread_id": "t456"}

        result = send_email(
            to="a@example.com",
            subject="Test",
            body_html="<p>Hi</p>",
            cc="b@example.com",
            bcc="c@example.com",
        )

        self.assertIsNotNone(result)
        mock_send.assert_called_once_with(
            to="a@example.com",
            subject="Test",
            body_html="<p>Hi</p>",
            cc="b@example.com",
            bcc="c@example.com",
            attachments=None,
        )

    @patch("mail.services.gmail.GmailService.send_message")
    def test_send_email_logs_failure(self, mock_send):
        mock_send.side_effect = Exception("API quota exceeded")

        with self.assertRaises(GmailServiceError):
            send_email(
                to="user@example.com",
                subject="Fail Test",
                body_html="<p>Test</p>",
            )

        log = EmailLog.objects.first()
        self.assertEqual(log.status, EmailLog.Status.FAILED)
        self.assertIn("API quota exceeded", log.error_message)

    @patch("mail.services.gmail.GmailService.send_message")
    def test_send_email_fail_silently(self, mock_send):
        mock_send.side_effect = Exception("API error")

        result = send_email(
            to="user@example.com",
            subject="Fail Silent",
            body_html="<p>Test</p>",
            fail_silently=True,
        )

        self.assertIsNone(result)
        self.assertEqual(EmailLog.objects.count(), 1)
        log = EmailLog.objects.first()
        self.assertEqual(log.status, EmailLog.Status.FAILED)

    def test_send_email_no_active_account(self):
        self.account.is_active = False
        self.account.save()

        with self.assertRaises(GmailServiceError) as ctx:
            send_email(
                to="user@example.com",
                subject="No Account",
                body_html="<p>Test</p>",
            )

        self.assertIn("No active", str(ctx.exception))

    def test_send_email_no_active_account_fail_silently(self):
        self.account.is_active = False
        self.account.save()

        result = send_email(
            to="user@example.com",
            subject="No Account",
            body_html="<p>Test</p>",
            fail_silently=True,
        )

        self.assertIsNone(result)
        self.assertEqual(EmailLog.objects.count(), 0)

    @patch("mail.services.gmail.GmailService.send_message")
    def test_send_email_updates_account_metadata(self, mock_send):
        mock_send.return_value = {"id": "msg789", "thread_id": "t789"}

        send_email(
            to="user@example.com",
            subject="Metadata Test",
            body_html="<p>Test</p>",
        )

        self.account.refresh_from_db()
        self.assertIsNotNone(self.account.last_used_at)
        self.assertEqual(self.account.last_error, "")

    @patch("mail.services.gmail.GmailService.send_message")
    def test_send_email_updates_error_on_failure(self, mock_send):
        mock_send.side_effect = Exception("Connection timeout")

        send_email(
            to="user@example.com",
            subject="Error Test",
            body_html="<p>Test</p>",
            fail_silently=True,
        )

        self.account.refresh_from_db()
        self.assertIn("Connection timeout", self.account.last_error)

    @patch("mail.services.gmail.GmailService.send_message")
    def test_send_email_with_user(self, mock_send):
        from django.contrib.auth import get_user_model

        # noinspection PyPep8Naming
        Member = get_user_model()
        admin = Member.objects.create_superuser(username="admin", email="admin@example.com", password="pass")
        mock_send.return_value = {"id": "msg_user", "thread_id": "t_user"}

        send_email(
            to="user@example.com",
            subject="User Test",
            body_html="<p>Test</p>",
            user=admin,
        )

        log = EmailLog.objects.first()
        self.assertEqual(log.performed_by, admin)
