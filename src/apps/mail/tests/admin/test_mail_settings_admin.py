"""The notification delivery settings admin."""

from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.core.models import AWSCredentialConfig, EmailServiceConfig, SMTPProviderConfig
from apps.event.tests.helpers import make_superuser


class MailSettingsAdminTest(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.config = EmailServiceConfig.objects.create(
            name="Production Mail",
            is_active=True,
            provider="ses",
            from_email="admin@example.com",
            from_name="I2G Admin",
            max_send_rate=12,
        )
        self.aws_config = AWSCredentialConfig.objects.create(
            name="Primary AWS",
            is_active=True,
            access_key_id="test-key",
            secret_access_key="test-secret",
            default_region="us-west-2",
            sms_from_number="+12065550000",
            sms_message_template="Your I2G code is {code}.",
        )
        self.smtp_config = SMTPProviderConfig.objects.create(
            name="Backup SMTP",
            is_active=True,
            host="smtp.example.com",
            port=587,
            username="mailer",
            password="existing-secret",
            use_tls=True,
        )

    def test_settings_page_shows_notification_delivery_config(self):
        response = self.client.get(reverse("admin:mail_settings"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Notification Delivery")
        self.assertContains(response, "AWS Identity and Access Management (IAM)")
        self.assertContains(response, "Primary AWS")
        self.assertContains(response, "Production Mail")
        self.assertContains(response, "Amazon Simple Email Service (us-west-2)")
        self.assertContains(response, "Amazon Simple Notification Service (us-west-2)")
        self.assertContains(response, "I2G Admin")
        self.assertContains(response, "admin@example.com")
        self.assertContains(response, "...-key")
        self.assertContains(response, "Configured")
        self.assertContains(response, "Your I2G code is {code}.")
        self.assertContains(response, 'href="/admin/mail/settings/edit/"')
        self.assertContains(response, 'href="/admin/mail/settings/test-email/"')
        self.assertContains(response, 'href="/admin/mail/settings/test-sms/"')
        self.assertNotContains(response, 'name="email-name"')
        self.assertNotContains(response, "Save Notification Delivery")
        self.assertNotContains(response, "Gmail Fallback")
        self.assertNotContains(response, "smtp.gmail.com")

    def test_settings_page_shows_not_configured_when_aws_is_missing(self):
        AWSCredentialConfig.objects.all().delete()

        response = self.client.get(reverse("admin:mail_settings"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Amazon Simple Email Service not configured")
        self.assertContains(response, "Amazon Simple Notification Service not configured")

    def test_settings_edit_view_renders_notification_delivery_form(self):
        response = self.client.get(reverse("admin:mail_settings_edit"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="email-name"')
        self.assertContains(response, 'name="aws-access_key_id"')
        self.assertContains(response, 'name="smtp-host"')
        self.assertNotContains(response, "existing-secret")
        self.assertContains(response, "Save Notification Delivery")
        self.assertContains(response, 'href="/admin/mail/settings/"')
        # Origination number is auto-detected from AWS, not hand-edited here.
        self.assertNotContains(response, 'name="aws-sms_from_number"')

    def test_settings_edit_post_updates_notification_delivery_config(self):
        response = self.client.post(
            reverse("admin:mail_settings_edit"),
            {
                "email-name": "Updated Mail",
                "email-is_active": "on",
                "email-provider": "smtp",
                "email-from_name": "Updated Sender",
                "email-from_email": "updated@example.com",
                "email-max_send_rate": "8",
                "aws-name": "Updated AWS",
                "aws-is_active": "on",
                "aws-access_key_id": "updated-key",
                "aws-secret_access_key": "updated-secret",
                "aws-default_region": "us-east-1",
                "aws-sms_message_template": "Code: {code}",
                "smtp-name": "Updated SMTP",
                "smtp-is_active": "on",
                "smtp-host": "mail.example.com",
                "smtp-port": "587",
                "smtp-username": "mailer",
                "smtp-password": "",
                "smtp-use_tls": "on",
                "smtp-timeout": "30",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("admin:mail_settings"))
        self.config.refresh_from_db()
        self.aws_config.refresh_from_db()
        self.assertEqual(self.config.name, "Updated Mail")
        self.smtp_config.refresh_from_db()
        self.assertEqual(self.config.provider, "smtp")
        self.assertEqual(self.config.from_email, "updated@example.com")
        self.assertEqual(self.config.max_send_rate, 8)
        self.assertEqual(self.smtp_config.password, "existing-secret")
        self.assertEqual(self.aws_config.name, "Updated AWS")
        self.assertEqual(self.aws_config.default_region, "us-east-1")
        self.assertEqual(self.aws_config.sms_message_template, "Code: {code}")
        # The manual override field is not part of the form; it stays untouched.
        self.assertEqual(self.aws_config.sms_from_number, "+12065550000")

    def _delivery_post_data(self, provider):
        data = {
            "email-name": "Updated Mail",
            "email-is_active": "on",
            "email-provider": provider,
            "email-from_name": "Updated Sender",
            "email-from_email": "updated@example.com",
            "email-max_send_rate": "8",
            "aws-name": "Updated AWS",
            "aws-is_active": "on",
            "aws-access_key_id": "updated-key",
            "aws-secret_access_key": "updated-secret",
            "aws-default_region": "us-east-1",
            "aws-sms_message_template": "Code: {code}",
        }
        if provider == "smtp":
            data.update(
                {
                    "smtp-name": "Updated SMTP",
                    "smtp-is_active": "on",
                    "smtp-host": "mail.example.com",
                    "smtp-port": "587",
                    "smtp-username": "mailer",
                    "smtp-password": "",
                    "smtp-use_tls": "on",
                    "smtp-timeout": "30",
                }
            )
        return data

    def test_ses_settings_are_editable_without_smtp_configuration(self):
        SMTPProviderConfig.objects.all().delete()

        response = self.client.get(reverse("admin:mail_settings_edit"))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["smtp_enabled"])
        self.assertIn("disabled", str(response.context["smtp_form"]["host"]))
        self.assertContains(response, 'id="smtp-provider-settings"')

        response = self.client.post(reverse("admin:mail_settings_edit"), self._delivery_post_data("ses"))

        self.assertRedirects(response, reverse("admin:mail_settings"), fetch_redirect_response=False)
        self.config.refresh_from_db()
        self.aws_config.refresh_from_db()
        self.assertEqual(self.config.from_email, "updated@example.com")
        self.assertEqual(self.aws_config.sms_message_template, "Code: {code}")
        self.assertEqual(self.aws_config.sms_from_number, "+12065550000")
        self.assertFalse(SMTPProviderConfig.objects.exists())

    def test_switching_providers_preserves_smtp_credentials(self):
        for provider in ("smtp", "ses", "smtp"):
            with self.subTest(provider=provider):
                data = self._delivery_post_data(provider)
                if provider == "ses":
                    # Disabled provider inputs must not overwrite retained settings.
                    data.update({"smtp-host": "", "smtp-port": "", "smtp-password": "ignored"})
                response = self.client.post(reverse("admin:mail_settings_edit"), data)

                self.assertRedirects(response, reverse("admin:mail_settings"), fetch_redirect_response=False)
                self.config.refresh_from_db()
                self.smtp_config.refresh_from_db()
                self.assertEqual(self.config.provider, provider)
                self.assertEqual(self.smtp_config.password, "existing-secret")
                self.assertEqual(self.smtp_config.host, "mail.example.com")
                self.assertTrue(self.smtp_config.is_active)

        response = self.client.get(reverse("admin:mail_settings_edit"))
        self.assertTrue(response.context["smtp_enabled"])
        self.assertFalse(response.context["smtp_form"].fields["host"].disabled)
        self.assertNotContains(response, "existing-secret")

    def test_blank_smtp_port_returns_form_error_without_changing_settings(self):
        data = self._delivery_post_data("smtp")
        data["smtp-port"] = ""

        response = self.client.post(reverse("admin:mail_settings_edit"), data)

        self.assertEqual(response.status_code, 200)
        self.assertIn("port", response.context["smtp_form"].errors)
        self.assertTrue(response.context["smtp_enabled"])
        self.config.refresh_from_db()
        self.aws_config.refresh_from_db()
        self.assertEqual(self.config.provider, "ses")
        self.assertEqual(self.aws_config.name, "Primary AWS")

    def test_inactive_smtp_provider_rolls_back_other_settings(self):
        data = self._delivery_post_data("smtp")
        data.pop("smtp-is_active")

        response = self.client.post(reverse("admin:mail_settings_edit"), data)

        self.assertEqual(response.status_code, 200)
        self.assertIn("provider", response.context["email_form"].errors)
        self.config.refresh_from_db()
        self.aws_config.refresh_from_db()
        self.smtp_config.refresh_from_db()
        self.assertEqual(self.config.provider, "ses")
        self.assertEqual(self.aws_config.name, "Primary AWS")
        self.assertEqual(self.smtp_config.host, "smtp.example.com")
        self.assertTrue(self.smtp_config.is_active)

    def test_test_email_view_renders_form(self):
        response = self.client.get(reverse("admin:mail_settings_test_email"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Send Test Email")
        self.assertContains(response, "admin@example.com")

    def test_test_sms_view_renders_form(self):
        response = self.client.get(reverse("admin:mail_settings_test_sms"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Send Test SMS")
        self.assertContains(response, "AWS End User Messaging")

    @patch("apps.mail.admin.settings.admin._send_test_email")
    def test_test_email_post_uses_active_mail_config(self, mock_send_test_email):
        mock_send_test_email.return_value = "AWS SES"

        response = self.client.post(reverse("admin:mail_settings_test_email"), {"recipient": "ops@example.com"})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("admin:mail_settings"))
        mock_send_test_email.assert_called_once()
        self.assertEqual(mock_send_test_email.call_args.kwargs["config"].pk, self.config.pk)
        self.assertEqual(mock_send_test_email.call_args.kwargs["recipient"], "ops@example.com")

    @patch("apps.mail.admin.settings.admin._send_test_sms")
    def test_test_sms_post_uses_notification_delivery_config(self, mock_send_test_sms):
        mock_send_test_sms.return_value = "message (ID: sns-1)"

        response = self.client.post(
            reverse("admin:mail_settings_test_sms"),
            {"country_code": "+1", "recipient": "2065550123"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("admin:mail_settings"))
        mock_send_test_sms.assert_called_once_with(phone_number="+12065550123")

    def test_test_email_post_without_recipient_shows_error(self):
        response = self.client.post(reverse("admin:mail_settings_test_email"), {"recipient": "  "}, follow=True)

        self.assertContains(response, "Please provide a recipient email address")

    @patch("apps.mail.admin.settings.admin._send_test_email", side_effect=RuntimeError("SES boom"))
    def test_test_email_post_reports_send_failure(self, mock_send):
        response = self.client.post(
            reverse("admin:mail_settings_test_email"), {"recipient": "ops@example.com"}, follow=True
        )

        self.assertContains(response, "Failed to send test email: SES boom")

    def test_test_sms_post_without_recipient_shows_error(self):
        response = self.client.post(
            reverse("admin:mail_settings_test_sms"), {"country_code": "+1", "recipient": ""}, follow=True
        )

        self.assertContains(response, "Please provide a phone number")

    @patch("apps.mail.admin.settings.admin._send_test_sms", side_effect=RuntimeError("SNS boom"))
    def test_test_sms_post_reports_send_failure(self, mock_send):
        response = self.client.post(
            reverse("admin:mail_settings_test_sms"),
            {"country_code": "+1", "recipient": "2065550123"},
            follow=True,
        )

        self.assertContains(response, "Failed to send test SMS: SNS boom")
