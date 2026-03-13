"""Tests for mail app admin views."""

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from mail.forms import ComposeForm, GoogleAccountForm
from mail.models import EmailLog, GoogleAccount, SESAccount, SESEmailLog
from mail.services.ses import SESServiceError

Member = get_user_model()

FAKE_SERVICE_JSON = '{"type":"service_account","project_id":"test","private_key":"key","client_email":"sa@test.iam.gserviceaccount.com"}'


@override_settings(ROOT_URLCONF="mail.tests.urls")
class GoogleAccountAdminTest(TestCase):
    """Tests for GoogleAccountAdmin views."""

    def setUp(self):
        self.admin_user = Member.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="testpass123",
        )
        self.client.login(username="admin", password="testpass123")
        self.account = GoogleAccount.objects.create(
            email="test@g.ucmerced.edu",
            display_name="ITG Test",
            service_account_json=FAKE_SERVICE_JSON,
            is_active=True,
        )

    def test_changelist_accessible(self):
        url = reverse("admin:mail_googleaccount_changelist")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_add_view_accessible(self):
        url = reverse("admin:mail_googleaccount_add")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    @patch("mail.admin.google_account.GmailService")
    def test_inbox_view(self, mock_service_cls):
        mock_service = MagicMock()
        mock_service.list_messages.return_value = {
            "messages": [
                {
                    "id": "msg1",
                    "thread_id": "t1",
                    "snippet": "Hello",
                    "label_ids": ["INBOX", "UNREAD"],
                    "is_unread": True,
                    "from": "sender@example.com",
                    "to": "test@g.ucmerced.edu",
                    "cc": "",
                    "subject": "Test Email",
                    "date": "Mon, 1 Jan 2026",
                    "message_id": "<msg1@example.com>",
                }
            ],
            "next_page_token": None,
        }
        mock_service_cls.return_value = mock_service

        url = reverse("admin:mail_inbox")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Inbox")

    @patch("mail.admin.google_account.GmailService")
    def test_sent_view(self, mock_service_cls):
        mock_service = MagicMock()
        mock_service.list_messages.return_value = {"messages": [], "next_page_token": None}
        mock_service_cls.return_value = mock_service

        url = reverse("admin:mail_sent")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sent")

    @patch("mail.admin.google_account.GmailService")
    def test_compose_view(self, mock_service_cls):
        url = reverse("admin:mail_compose")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Compose")

    @patch("mail.admin.google_account.GmailService")
    def test_message_detail_view(self, mock_service_cls):
        mock_service = MagicMock()
        mock_service.get_message.return_value = {
            "id": "msg1",
            "thread_id": "t1",
            "label_ids": ["INBOX"],
            "is_unread": False,
            "snippet": "Hello",
            "body_html": "<p>Hello World</p>",
            "body_plain": "Hello World",
            "attachments": [],
            "from": "sender@example.com",
            "to": "test@g.ucmerced.edu",
            "cc": "",
            "subject": "Test Email",
            "date": "Mon, 1 Jan 2026",
            "message_id": "<msg1@example.com>",
        }
        mock_service_cls.return_value = mock_service

        url = reverse("admin:mail_message_detail", args=["msg1"])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Email")

    @patch("mail.admin.google_account.GmailService")
    def test_send_action_success(self, mock_service_cls):
        mock_service = MagicMock()
        mock_service.send_message.return_value = {"id": "sent1", "thread_id": "t1"}
        mock_service_cls.return_value = mock_service

        url = reverse("admin:mail_send")
        response = self.client.post(
            url,
            {
                "to": "recipient@example.com",
                "subject": "Test",
                "body": "<p>Hello</p>",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(EmailLog.objects.count(), 1)
        log = EmailLog.objects.first()
        self.assertEqual(log.action, EmailLog.Action.SEND)
        self.assertEqual(log.status, EmailLog.Status.SUCCESS)

    @patch("mail.admin.google_account.GmailService")
    def test_trash_action(self, mock_service_cls):
        mock_service = MagicMock()
        mock_service_cls.return_value = mock_service

        url = reverse("admin:mail_trash", args=["msg1"])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(EmailLog.objects.count(), 1)
        log = EmailLog.objects.first()
        self.assertEqual(log.action, EmailLog.Action.DELETE)

    def test_inbox_no_active_account(self):
        self.account.is_active = False
        self.account.save()
        url = reverse("admin:mail_inbox")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    @patch("mail.admin.google_account.GmailService")
    def test_attachment_download_sanitizes_filename(self, mock_service_cls):
        """S8 fix: Content-Disposition filename is sanitized to remove injection chars."""
        mock_service = MagicMock()
        mock_service.get_attachment.return_value = (
            '"evil\r\n/file\\name.pdf"',
            b"%PDF-1.5 fake content",
        )
        mock_service_cls.return_value = mock_service

        url = reverse("admin:mail_attachment", args=["msg1", "att1"])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        disposition = response["Content-Disposition"]
        # Verify dangerous characters were replaced with underscores
        self.assertNotIn('"evil', disposition.split("filename=")[1].strip('"'))
        self.assertNotIn("\r", disposition)
        self.assertNotIn("\n", disposition)
        self.assertNotIn("/", disposition.split("filename=")[1])
        self.assertNotIn("\\", disposition.split("filename=")[1])

    def test_emaillog_changelist_accessible(self):
        url = reverse("admin:mail_emaillog_changelist")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


class GoogleAccountFormTest(TestCase):
    """Tests for GoogleAccountForm validation."""

    def test_valid_json(self):
        form = GoogleAccountForm(
            data={
                "email": "test@example.com",
                "service_account_json": FAKE_SERVICE_JSON,
                "is_active": True,
            }
        )
        self.assertTrue(form.is_valid())

    def test_invalid_json(self):
        form = GoogleAccountForm(
            data={
                "email": "test@example.com",
                "service_account_json": "not json",
                "is_active": True,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("service_account_json", form.errors)

    def test_missing_required_keys(self):
        form = GoogleAccountForm(
            data={
                "email": "test@example.com",
                "service_account_json": '{"type":"service_account"}',
                "is_active": True,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("Missing required keys", form.errors["service_account_json"][0])

    def test_wrong_type(self):
        form = GoogleAccountForm(
            data={
                "email": "test@example.com",
                "service_account_json": '{"type":"authorized_user","project_id":"t","private_key":"k","client_email":"e"}',
                "is_active": True,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("service_account", form.errors["service_account_json"][0])


class ComposeFormTest(TestCase):
    """Tests for ComposeForm validation."""

    def test_valid_compose(self):
        form = ComposeForm(
            data={
                "to": "user@example.com",
                "subject": "Test",
                "body": "<p>Hello</p>",
            }
        )
        self.assertTrue(form.is_valid())


@override_settings(
    ROOT_URLCONF="mail.tests.urls",
    SES_AWS_ACCESS_KEY_ID="ses-access-key",
    SES_AWS_SECRET_ACCESS_KEY="ses-secret-key",
    SES_AWS_REGION="us-west-2",
)
class SESAccountAdminTest(TestCase):
    """Tests for the SES sender admin views."""

    def setUp(self):
        self.admin_user = Member.objects.create_superuser(
            username="ses-admin",
            email="ses-admin@example.com",
            password="testpass123",
        )
        self.client.login(username="ses-admin", password="testpass123")
        SESAccount.all_objects.all().hard_delete()
        self.account = SESAccount.objects.create(
            display_name="Innovate to Grow",
            is_active=True,
        )

    def test_changelist_accessible(self):
        response = self.client.get(reverse("admin:mail_sesaccount_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Compose SES Email")

    def test_compose_view_accessible(self):
        response = self.client.get(reverse("admin:mail_ses_compose"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Compose SES Email")
        self.assertContains(response, "i2g@g.ucmerced.edu")

    @patch("mail.admin.ses_account.SESService")
    def test_send_action_success(self, mock_service_cls):
        mock_service = MagicMock()
        mock_service.send_message.return_value = {"id": "ses-msg-123"}
        mock_service_cls.return_value = mock_service

        response = self.client.post(
            reverse("admin:mail_ses_send"),
            {
                "to": "recipient@example.com",
                "subject": "SES Test",
                "body": "<p>Hello</p>",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("admin:mail_sesemaillog_changelist"))
        self.assertEqual(SESEmailLog.objects.count(), 1)
        self.assertEqual(EmailLog.objects.count(), 1)
        log = SESEmailLog.objects.first()
        self.assertEqual(log.status, SESEmailLog.Status.SUCCESS)
        self.assertEqual(log.recipients, "recipient@example.com")
        self.assertEqual(log.ses_message_id, "ses-msg-123")
        generic_log = EmailLog.objects.first()
        self.assertEqual(generic_log.status, EmailLog.Status.SUCCESS)
        self.assertEqual(generic_log.recipients, "recipient@example.com")
        self.assertEqual(generic_log.gmail_message_id, "ses-msg-123")

    @patch("mail.admin.ses_account.SESService")
    def test_send_action_failure(self, mock_service_cls):
        mock_service = MagicMock()
        mock_service.send_message.side_effect = SESServiceError("SES down")
        mock_service_cls.return_value = mock_service

        response = self.client.post(
            reverse("admin:mail_ses_send"),
            {
                "to": "recipient@example.com",
                "subject": "SES Test",
                "body": "<p>Hello</p>",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(SESEmailLog.objects.count(), 1)
        self.assertEqual(EmailLog.objects.count(), 1)
        log = SESEmailLog.objects.first()
        self.assertEqual(log.status, SESEmailLog.Status.FAILED)
        generic_log = EmailLog.objects.first()
        self.assertEqual(generic_log.status, EmailLog.Status.FAILED)
        self.assertContains(response, "Failed to send SES email")

    def test_sesemaillog_changelist_shows_entries(self):
        SESEmailLog.objects.create(
            account=self.account,
            action=SESEmailLog.Action.SEND,
            status=SESEmailLog.Status.SUCCESS,
            ses_message_id="ses-msg-123",
            subject="SES test subject",
            recipients="recipient@example.com",
            performed_by=self.admin_user,
        )

        response = self.client.get(reverse("admin:mail_sesemaillog_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SES test subject")

    def test_required_fields(self):
        form = ComposeForm(data={})
        self.assertFalse(form.is_valid())
        self.assertIn("to", form.errors)
        self.assertIn("subject", form.errors)
        self.assertIn("body", form.errors)

    def test_optional_fields(self):
        form = ComposeForm(
            data={
                "to": "user@example.com",
                "subject": "Test",
                "body": "Hello",
                "cc": "cc@example.com",
                "bcc": "bcc@example.com",
                "thread_id": "t1",
                "in_reply_to": "<msg@example.com>",
                "references": "<msg@example.com>",
            }
        )
        self.assertTrue(form.is_valid())
