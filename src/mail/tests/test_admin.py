from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from core.models import EmailServiceConfig, GoogleCredentialConfig
from event.tests.helpers import make_superuser
from mail.models import EmailCampaign
from mail.services.preview import HTML_MARKER


class EmailCampaignAdminImportTest(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.campaign = EmailCampaign.objects.create(subject="Spring Update", body="Draft body")
        self.google_config = GoogleCredentialConfig.objects.create(
            name="Primary Google",
            is_active=True,
            credentials_json={
                "type": "service_account",
                "project_id": "innovate-prod",
                "private_key": "-----BEGIN PRIVATE KEY-----\\nabc\\n-----END PRIVATE KEY-----\\n",
                "client_email": "mailer@innovate-prod.iam.gserviceaccount.com",
                "token_uri": "https://oauth2.googleapis.com/token",
            },
        )
        self.email_config = EmailServiceConfig.objects.create(
            name="Primary SES",
            is_active=True,
            ses_access_key_id="AKIAXXXXXXXX",
            ses_secret_access_key="secret",
            ses_region="us-west-2",
            ses_from_email="i2g@g.ucmerced.edu",
            ses_from_name="Innovate to Grow",
        )

    def test_changelist_shows_loaded_google_service_account_and_mailboxes(self):
        response = self.client.get(reverse("admin:mail_emailcampaign_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Gmail Import Account")
        self.assertContains(response, "mailer@innovate-prod.iam.gserviceaccount.com")
        self.assertContains(response, "i2g@g.ucmerced.edu")
        self.assertContains(response, "Innovate to Grow &lt;i2g@g.ucmerced.edu&gt;")

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
        self.assertContains(response, "Sent Newsletter")
        self.assertContains(response, "Import will replace the current campaign body")
        self.assertContains(response, "mailer@innovate-prod.iam.gserviceaccount.com")
        self.assertContains(response, "innovate-prod")

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
        mock_import.assert_called_once()
        self.campaign.refresh_from_db()
        self.assertTrue(self.campaign.body.startswith(HTML_MARKER))
        self.assertIn("Imported from Gmail", self.campaign.body)

    def test_send_preview_remains_available_for_imported_html(self):
        self.campaign.body = HTML_MARKER + "<p><strong>Imported</strong> HTML</p>"
        self.campaign.save(update_fields=["body", "updated_at"])

        response = self.client.get(reverse("admin:mail_emailcampaign_send_preview", args=[self.campaign.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Preview Email")
