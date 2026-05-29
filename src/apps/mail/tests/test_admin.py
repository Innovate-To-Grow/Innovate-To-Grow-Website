from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.mail.admin.campaign import EmailCampaignAdmin
from apps.mail.models import EmailCampaign
from apps.mail.services import GMAIL_FOLDER_DISPLAY
from apps.mail.services.preview import HTML_MARKER
from cms.models import CMSPage
from core.models import AWSCredentialConfig, EmailServiceConfig, GmailAccessAccount
from event.tests.helpers import make_superuser


class MailSettingsAdminTest(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.config = EmailServiceConfig.objects.create(
            name="Production Mail",
            is_active=True,
            ses_from_email="admin@example.com",
            ses_from_name="I2G Admin",
            ses_max_send_rate=12,
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
        self.assertContains(response, "Save Notification Delivery")
        self.assertContains(response, 'href="/admin/mail/settings/"')

    def test_settings_edit_post_updates_notification_delivery_config(self):
        response = self.client.post(
            reverse("admin:mail_settings_edit"),
            {
                "email-name": "Updated Mail",
                "email-is_active": "on",
                "email-ses_from_name": "Updated Sender",
                "email-ses_from_email": "updated@example.com",
                "email-ses_max_send_rate": "8",
                "aws-name": "Updated AWS",
                "aws-is_active": "on",
                "aws-access_key_id": "updated-key",
                "aws-secret_access_key": "updated-secret",
                "aws-default_region": "us-east-1",
                "aws-sms_from_number": "+12065550123",
                "aws-sms_message_template": "Code: {code}",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("admin:mail_settings"))
        self.config.refresh_from_db()
        self.aws_config.refresh_from_db()
        self.assertEqual(self.config.name, "Updated Mail")
        self.assertEqual(self.config.ses_from_email, "updated@example.com")
        self.assertEqual(self.config.ses_max_send_rate, 8)
        self.assertEqual(self.aws_config.name, "Updated AWS")
        self.assertEqual(self.aws_config.default_region, "us-east-1")
        self.assertEqual(self.aws_config.sms_from_number, "+12065550123")

    def test_test_email_view_renders_form(self):
        response = self.client.get(reverse("admin:mail_settings_test_email"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Send Test Email")
        self.assertContains(response, "admin@example.com")

    def test_test_sms_view_renders_form(self):
        response = self.client.get(reverse("admin:mail_settings_test_sms"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Send Test SMS")
        self.assertContains(response, "AWS SNS")

    @patch("apps.mail.admin.settings._send_test_email")
    def test_test_email_post_uses_active_mail_config(self, mock_send_test_email):
        mock_send_test_email.return_value = "AWS SES"

        response = self.client.post(reverse("admin:mail_settings_test_email"), {"recipient": "ops@example.com"})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("admin:mail_settings"))
        mock_send_test_email.assert_called_once()
        self.assertEqual(mock_send_test_email.call_args.kwargs["config"].pk, self.config.pk)
        self.assertEqual(mock_send_test_email.call_args.kwargs["recipient"], "ops@example.com")

    @patch("apps.mail.admin.settings._send_test_sms")
    def test_test_sms_post_uses_notification_delivery_config(self, mock_send_test_sms):
        mock_send_test_sms.return_value = "message (ID: sns-1)"

        response = self.client.post(
            reverse("admin:mail_settings_test_sms"),
            {"country_code": "+1", "recipient": "2065550123"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("admin:mail_settings"))
        mock_send_test_sms.assert_called_once_with(phone_number="+12065550123")


class EmailCampaignAdminImportTest(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.campaign = EmailCampaign.objects.create(
            subject="Spring Update",
            body="Draft body",
            login_redirect_path="/account",
        )
        self.gmail_import_config = GmailAccessAccount.objects.create(
            name="Primary Gmail Access Account",
            is_active=True,
            imap_host="imap.gmail.com",
            gmail_username="campaigns@ucmerced.edu",
            gmail_password="app-password",
        )
        from core.models import AWSCredentialConfig

        AWSCredentialConfig.objects.all().delete()
        self.aws_config = AWSCredentialConfig.objects.create(
            name="Primary AWS",
            is_active=True,
            access_key_id="AKIAXXXXXXXX",
            secret_access_key="secret",
            default_region="us-west-2",
        )
        self.email_config = EmailServiceConfig.objects.create(
            name="Primary SES",
            is_active=True,
            ses_from_email="campaigns@ucmerced.edu",
            ses_from_name="Innovate to Grow",
        )

    def test_changelist_shows_loaded_gmail_import_account_and_mailboxes(self):
        response = self.client.get(reverse("admin:mail_emailcampaign_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Gmail Access Account")
        self.assertContains(response, "imap.gmail.com")
        self.assertContains(response, "campaigns@ucmerced.edu")
        self.assertContains(response, GMAIL_FOLDER_DISPLAY)
        self.assertContains(response, "Innovate to Grow &lt;campaigns@ucmerced.edu&gt;")
        self.assertContains(response, 'href="/admin/mail/settings/"')
        self.assertContains(response, "Edit Notification Delivery")

    def test_import_gmail_html_view_renders_recent_messages(self):
        with patch("apps.mail.admin.campaign.list_recent_sent_messages") as mock_list:
            mock_list.return_value = [
                {
                    "message_id": "msg-1",
                    "subject": "Sent Newsletter",
                    "sent_at": "2026-04-06 09:00 AM PDT",
                    "snippet": "Recent Gmail snippet",
                    "has_html": True,
                }
            ]

            response = self.client.get(reverse("admin:mail_emailcampaign_import_gmail_html", args=[self.campaign.pk]))

        self.assertEqual(response.status_code, 200)
        mock_list.assert_called_once_with(limit=5, mailbox="campaigns@ucmerced.edu", force_refresh=False)
        self.assertContains(response, "Sent Newsletter")
        self.assertContains(response, "Import will replace the current campaign body")
        self.assertContains(response, "imap.gmail.com")
        self.assertContains(response, "campaigns@ucmerced.edu")
        self.assertContains(response, GMAIL_FOLDER_DISPLAY)

    def test_import_gmail_html_view_redirects_for_non_draft_campaign(self):
        self.campaign.status = "sent"
        self.campaign.save(update_fields=["status", "updated_at"])

        response = self.client.get(reverse("admin:mail_emailcampaign_import_gmail_html", args=[self.campaign.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("admin:mail_emailcampaign_change", args=[self.campaign.pk]),
        )

    def test_import_gmail_html_confirm_overwrites_body(self):
        def _fake_import(campaign, message_id, mailbox):
            campaign.body = HTML_MARKER + "<p>Imported from Gmail</p>"
            campaign.save(update_fields=["body", "updated_at"])
            return campaign.body

        with patch("apps.mail.admin.campaign.import_message_into_campaign", side_effect=_fake_import) as mock_import:
            response = self.client.post(
                reverse("admin:mail_emailcampaign_import_gmail_html_confirm", args=[self.campaign.pk]),
                {"message_id": "msg-1"},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("admin:mail_emailcampaign_change", args=[self.campaign.pk]),
        )
        mock_import.assert_called_once_with(self.campaign, "msg-1", mailbox="campaigns@ucmerced.edu")
        self.campaign.refresh_from_db()
        self.assertTrue(self.campaign.body.startswith(HTML_MARKER))
        self.assertIn("Imported from Gmail", self.campaign.body)

    def test_send_preview_remains_available_for_imported_html(self):
        self.campaign.body = HTML_MARKER + "<p><strong>Imported</strong> HTML</p>"
        self.campaign.save(update_fields=["body", "updated_at"])

        response = self.client.get(reverse("admin:mail_emailcampaign_send_preview", args=[self.campaign.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Preview Email")

    def test_change_view_renders_for_sent_campaign(self):
        self.campaign.status = "sent"
        self.campaign.login_redirect_path = "/event-registration"
        self.campaign.save(update_fields=["status", "login_redirect_path", "updated_at"])

        response = self.client.get(reverse("admin:mail_emailcampaign_change", args=[self.campaign.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.campaign.subject)


class EmailCampaignAdminRedirectTest(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.request_factory = RequestFactory()
        self.model_admin = EmailCampaignAdmin(EmailCampaign, AdminSite())
        self.published_page = CMSPage.objects.create(
            slug="campaign-destination",
            route="/campaign-destination",
            title="Campaign Destination",
            status="published",
        )
        self.archived_page = CMSPage.objects.create(
            slug="old-campaign-destination",
            route="/old-campaign-destination",
            title="Old Campaign Destination",
            status="archived",
        )

    def test_new_campaign_form_requires_redirect_destination(self):
        form = self._get_form(
            data={
                "audience_type": "subscribers",
                "member_email_scope": "primary",
                "subject": "Spring Update",
                "body_format": "plain",
                "body": "Draft body",
                "login_redirect_path": "",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("login_redirect_path", form.errors)

    def test_redirect_choices_include_account_app_routes_and_published_cms_pages(self):
        form = self._get_form()
        choices = dict(form.fields["login_redirect_path"].choices)

        self.assertIn("/account", choices)
        self.assertIn("/schedule", choices)
        self.assertIn("/campaign-destination", choices)
        self.assertNotIn("/old-campaign-destination", choices)

    def test_sent_campaign_marks_redirect_destination_read_only(self):
        campaign = EmailCampaign.objects.create(
            subject="Sent Update",
            body="Sent body",
            login_redirect_path="/campaign-destination",
            status="sent",
        )

        readonly_fields = self.model_admin.get_readonly_fields(self._build_request(), obj=campaign)

        self.assertIn("login_redirect_path", readonly_fields)

    def _get_form(self, *, data=None, instance=None):
        form_class = self.model_admin.get_form(self._build_request(), obj=instance)
        return form_class(data=data, instance=instance)

    def _build_request(self):
        request = self.request_factory.get("/admin/mail/emailcampaign/")
        request.user = self.admin_user
        return request
