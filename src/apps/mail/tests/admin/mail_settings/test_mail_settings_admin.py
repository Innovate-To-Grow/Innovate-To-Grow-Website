"""The notification delivery settings admin."""

from django.test import TestCase
from django.urls import reverse

from apps.core.models import AWSCredentialConfig, EmailServiceConfig, SMTPProviderConfig
from apps.event.tests.helpers import make_superuser


class _MailSettingsAdminCase(TestCase):
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


class MailSettingsAdminTest(_MailSettingsAdminCase):
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
                "email-max_send_rate": "8",  # no longer a form field: ignored
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
        # The old campaign rate is not editable any more (Mail → Delivery Rates has the rates).
        self.assertEqual(self.config.max_send_rate, 12)
        self.assertEqual(self.smtp_config.password, "existing-secret")
        self.assertEqual(self.aws_config.name, "Updated AWS")
        self.assertEqual(self.aws_config.default_region, "us-east-1")
        self.assertEqual(self.aws_config.sms_message_template, "Code: {code}")
        # The manual override field is not part of the form; it stays untouched.
        self.assertEqual(self.aws_config.sms_from_number, "+12065550000")

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
