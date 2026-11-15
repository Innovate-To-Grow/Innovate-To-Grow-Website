from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.core.models import GmailAccessAccount
from apps.event.tests.helpers import make_superuser
from apps.mail.admin.campaign.admin.inlines import AudienceTypeFilter, RecipientLogInline
from apps.mail.models import EmailCampaign
from apps.mail.services.campaign.content.preview import HTML_MARKER
from apps.mail.services.campaign.gmail_import import GmailImportError
from apps.mail.tests.admin.campaign.views.test_campaign_views import _make_email_config


class CampaignGmailViewTests(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        GmailAccessAccount.objects.create(
            name="Gmail",
            is_active=True,
            imap_host="imap.gmail.com",
            gmail_username="campaigns@ucmerced.edu",
            gmail_password="app-password",
        )
        _make_email_config()
        self.campaign = EmailCampaign.objects.create(subject="s", body="b", status="draft")

    def test_import_view_redirects_for_non_draft(self):
        self.campaign.status = "sent"
        self.campaign.save(update_fields=["status", "updated_at"])

        response = self.client.get(reverse("admin:mail_emailcampaign_import_gmail_html", args=[self.campaign.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("admin:mail_emailcampaign_change", args=[self.campaign.pk]))

    @patch(
        "apps.mail.admin.campaign.views.services.list_recent_sent_messages", side_effect=GmailImportError("imap down")
    )
    def test_import_view_handles_gmail_import_error(self, mock_list):
        response = self.client.get(
            reverse("admin:mail_emailcampaign_import_gmail_html", args=[self.campaign.pk]), follow=True
        )

        self.assertContains(response, "imap down")
        mock_list.assert_called_once()

    def test_import_confirm_redirects_for_non_draft(self):
        self.campaign.status = "sent"
        self.campaign.save(update_fields=["status", "updated_at"])

        response = self.client.post(
            reverse("admin:mail_emailcampaign_import_gmail_html_confirm", args=[self.campaign.pk]),
            {"message_id": "msg-1"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("admin:mail_emailcampaign_change", args=[self.campaign.pk]))

    def test_import_confirm_get_redirects_to_selection(self):
        response = self.client.get(
            reverse("admin:mail_emailcampaign_import_gmail_html_confirm", args=[self.campaign.pk])
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("admin:mail_emailcampaign_import_gmail_html", args=[self.campaign.pk]))

    def test_import_confirm_requires_message_id(self):
        response = self.client.post(
            reverse("admin:mail_emailcampaign_import_gmail_html_confirm", args=[self.campaign.pk]),
            {"message_id": "   "},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("admin:mail_emailcampaign_import_gmail_html", args=[self.campaign.pk]))

    @patch(
        "apps.mail.admin.campaign.views.services.import_message_into_campaign", side_effect=GmailImportError("no html")
    )
    def test_import_confirm_handles_import_error(self, mock_import):
        response = self.client.post(
            reverse("admin:mail_emailcampaign_import_gmail_html_confirm", args=[self.campaign.pk]),
            {"message_id": "msg-1"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("admin:mail_emailcampaign_import_gmail_html", args=[self.campaign.pk]))
        mock_import.assert_called_once()

    @patch("apps.mail.admin.campaign.views.services.import_message_into_campaign")
    def test_import_confirm_success(self, mock_import):
        def _do_import(campaign, message_id, mailbox):
            campaign.body = HTML_MARKER + "<p>Imported</p>"
            campaign.save(update_fields=["body", "updated_at"])

        mock_import.side_effect = _do_import

        response = self.client.post(
            reverse("admin:mail_emailcampaign_import_gmail_html_confirm", args=[self.campaign.pk]),
            {"message_id": "msg-1"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("admin:mail_emailcampaign_change", args=[self.campaign.pk]))
        mock_import.assert_called_once()


class CampaignInlineTests(TestCase):
    def test_recipient_log_inline_no_add_permission(self):
        inline = RecipientLogInline(EmailCampaign, AdminSite())
        request = RequestFactory().get("/")

        self.assertFalse(inline.has_add_permission(request))

    def test_audience_type_filter_lookups(self):
        from apps.mail.models.email.campaign_options import ALL_AUDIENCE_CHOICES

        instance = AudienceTypeFilter.__new__(AudienceTypeFilter)
        self.assertEqual(instance.lookups(request=None, model_admin=None), ALL_AUDIENCE_CHOICES)


class CampaignChangelistFilterTests(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        _make_email_config()

    def test_changelist_filters_by_audience_type(self):
        EmailCampaign.objects.create(subject="Subs", body="b", audience_type="subscribers")
        EmailCampaign.objects.create(subject="Staff", body="b", audience_type="staff")

        response = self.client.get(reverse("admin:mail_emailcampaign_changelist"), {"audience_type": "subscribers"})

        self.assertEqual(response.status_code, 200)
        subjects = {c.subject for c in response.context["cl"].queryset}
        self.assertEqual(subjects, {"Subs"})
