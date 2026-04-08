from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase
from django.urls import reverse

from cms.models import CMSPage
from core.models import EmailServiceConfig, GmailImportConfig
from event.tests.helpers import make_superuser
from mail.admin.campaign import EmailCampaignAdmin
from mail.models import EmailCampaign
from mail.services import GMAIL_FOLDER_DISPLAY
from mail.services.preview import HTML_MARKER


class EmailCampaignAdminImportTest(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.campaign = EmailCampaign.objects.create(
            subject="Spring Update",
            body="Draft body",
            login_redirect_path="/account",
        )
        self.gmail_import_config = GmailImportConfig.objects.create(
            name="Primary Gmail Import",
            is_active=True,
            imap_host="imap.gmail.com",
            gmail_username="campaigns@ucmerced.edu",
            gmail_password="app-password",
        )
        self.email_config = EmailServiceConfig.objects.create(
            name="Primary SES",
            is_active=True,
            ses_access_key_id="AKIAXXXXXXXX",
            ses_secret_access_key="secret",
            ses_region="us-west-2",
            ses_from_email="campaigns@ucmerced.edu",
            ses_from_name="Innovate to Grow",
        )

    def test_changelist_shows_loaded_gmail_import_account_and_mailboxes(self):
        response = self.client.get(reverse("admin:mail_emailcampaign_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Gmail Import Account")
        self.assertContains(response, "imap.gmail.com")
        self.assertContains(response, "campaigns@ucmerced.edu")
        self.assertContains(response, GMAIL_FOLDER_DISPLAY)
        self.assertContains(response, "Innovate to Grow &lt;campaigns@ucmerced.edu&gt;")

    def test_import_gmail_html_view_renders_recent_messages(self):
        with patch("mail.admin.campaign.list_recent_sent_messages") as mock_list:
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
        mock_list.assert_called_once_with(limit=5, mailbox="campaigns@ucmerced.edu")
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

        with patch("mail.admin.campaign.import_message_into_campaign", side_effect=_fake_import) as mock_import:
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
