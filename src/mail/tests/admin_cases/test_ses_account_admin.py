"""Tests for mail app admin views."""

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from mail.forms import ComposeForm
from mail.models import EmailLog, SESAccount, SESEmailLog
from mail.services.ses import SESServiceError

Member = get_user_model()

FAKE_SERVICE_JSON = '{"type":"service_account","project_id":"test","private_key":"key","client_email":"sa@test.iam.gserviceaccount.com"}'


@override_settings(ROOT_URLCONF="mail.tests.urls")
class SESAccountAdminTest(TestCase):
    """Tests for the SES sender admin views."""

    # noinspection PyPep8Naming
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
                "recipient_source": "manual",
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
                "recipient_source": "manual",
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
        form = ComposeForm(data={"recipient_source": "manual"})
        self.assertFalse(form.is_valid())
        self.assertIn("to", form.errors)
        self.assertIn("subject", form.errors)
        self.assertIn("body", form.errors)

    def test_optional_fields(self):
        form = ComposeForm(
            data={
                "recipient_source": "manual",
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

    def test_preview_action_returns_html(self):
        response = self.client.post(
            reverse("admin:mail_ses_preview"),
            {"body": "<p>Preview content</p>"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/html")
        content = response.content.decode()
        self.assertIn("<p>Preview content</p>", content)
        self.assertIn("Innovate to Grow", content)
        self.assertIn("UC Merced", content)
        # Should use data URI for logo, not CID
        self.assertIn("data:image/png;base64,", content)
        self.assertNotIn("cid:i2g-logo", content)

    def test_preview_action_get_redirects(self):
        response = self.client.get(reverse("admin:mail_ses_preview"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("admin:mail_ses_compose"))

    @patch("mail.admin.ses_account.SESService")
    def test_send_wraps_body_in_layout(self, mock_service_cls):
        mock_service = MagicMock()
        mock_service.send_message.return_value = {"id": "ses-msg-456"}
        mock_service_cls.return_value = mock_service

        self.client.post(
            reverse("admin:mail_ses_send"),
            {
                "recipient_source": "manual",
                "to": "recipient@example.com",
                "subject": "Layout Test",
                "body": "<p>My content</p>",
            },
        )

        mock_service.send_message.assert_called_once()
        call_kwargs = mock_service.send_message.call_args
        body_html = call_kwargs.kwargs.get("body_html") or call_kwargs[1].get("body_html")
        # Body should be wrapped in layout
        self.assertIn("<p>My content</p>", body_html)
        self.assertIn("Innovate to Grow", body_html)
        # Should include inline images with logo
        inline_images = call_kwargs.kwargs.get("inline_images") or call_kwargs[1].get("inline_images")
        self.assertIsNotNone(inline_images)
        self.assertEqual(len(inline_images), 1)
        cid, filename, data = inline_images[0]
        self.assertEqual(cid, "i2g-logo")
        self.assertEqual(filename, "i2glogo.png")
