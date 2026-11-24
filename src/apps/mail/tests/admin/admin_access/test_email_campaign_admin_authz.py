from unittest.mock import patch

from django.urls import reverse

from apps.mail.models import EmailCampaign
from apps.mail.tests.admin.admin_access.test_admin_authz import MailAdminAuthzTestBase


class EmailCampaignAdminAuthzTest(MailAdminAuthzTestBase):
    def setUp(self):
        super().setUp()
        self.campaign = EmailCampaign.objects.create(
            name="News",
            subject="Hello",
            body="Body",
            audience_type="manual",
            manual_emails="a@example.com",
            status="draft",
        )

    def test_preview_recipients_refused_to_members_allowed_for_admins(self):
        url = reverse("admin:mail_emailcampaign_preview_recipients", args=[self.campaign.pk])
        self.assert_refused_to_member(url)
        self.assert_allowed_for_admin(url)

    def test_send_preview_refused_to_members_allowed_for_admins(self):
        url = reverse("admin:mail_emailcampaign_send_preview", args=[self.campaign.pk])
        self.assert_refused_to_member(url)
        self.assert_allowed_for_admin(url)

    def test_send_confirm_get_refused_to_members_allowed_for_admins(self):
        url = reverse("admin:mail_emailcampaign_send_confirm", args=[self.campaign.pk])
        self.assert_refused_to_member(url)
        self.assert_allowed_for_admin(url)

    def test_send_confirm_post_refused_to_members(self):
        url = reverse("admin:mail_emailcampaign_send_confirm", args=[self.campaign.pk])
        self.assert_refused_to_member(url, method="post", data={"confirmation_text": self.campaign.name})
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, "draft")

    def test_status_refused_to_members_allowed_for_admins(self):
        url = reverse("admin:mail_emailcampaign_send_status", args=[self.campaign.pk])
        self.assert_refused_to_member(url)
        self.assert_allowed_for_admin(url)

    def test_status_json_refused_to_members_allowed_for_admins(self):
        url = reverse("admin:mail_emailcampaign_send_status_json", args=[self.campaign.pk])
        self.assert_refused_to_member(url)
        response = self.assert_allowed_for_admin(url)
        self.assertEqual(response.status_code, 200)

    def test_inline_preview_refused_to_members(self):
        url = reverse("admin:mail_emailcampaign_inline_preview")
        self.assert_refused_to_member(url, method="post", data={"body": "hi", "body_format": "plain"})

    def test_inline_preview_allowed_for_admins(self):
        url = reverse("admin:mail_emailcampaign_inline_preview")
        response = self.assert_allowed_for_admin(url, method="post", data={"body": "hi", "body_format": "plain"})
        self.assertEqual(response.status_code, 200)

    @patch("apps.mail.admin.campaign.views.services.list_recent_sent_messages")
    @patch("apps.mail.admin.campaign.views.services.resolve_gmail_mailbox")
    def test_import_gmail_html_refused_to_members_allowed_for_admins(self, mock_mailbox, mock_list):
        mock_mailbox.return_value = "inbox@example.com"
        mock_list.return_value = []
        url = reverse("admin:mail_emailcampaign_import_gmail_html", args=[self.campaign.pk])
        # Denied before any Gmail service call.
        self.assert_refused_to_member(url)
        mock_list.assert_not_called()
        self.assert_allowed_for_admin(url)

    def test_import_gmail_html_confirm_refused_to_members(self):
        url = reverse("admin:mail_emailcampaign_import_gmail_html_confirm", args=[self.campaign.pk])
        self.assert_refused_to_member(url, method="post", data={"message_id": "abc"})

    def test_duplicate_refused_to_members_allowed_for_admins(self):
        url = reverse("admin:mail_emailcampaign_duplicate_campaign_action", args=[self.campaign.pk])
        self.assert_refused_to_member(url)
        self.assert_refused_to_member(url, method="post", data={"name": "Copy", "audience": "same"})
        self.assertEqual(EmailCampaign.objects.count(), 1)
        self.assert_allowed_for_admin(url)
        self.assert_allowed_for_admin(url, method="post", data={"name": "Copy", "audience": "same"})
        self.assertEqual(EmailCampaign.objects.count(), 2)


class InboxAdminAuthzTest(MailAdminAuthzTestBase):
    def test_inbox_list_refused_to_members_allowed_for_admins(self):
        url = reverse("admin:mail_inbox_list")
        self.assert_refused_to_member(url)
        self.assert_allowed_for_admin(url)

    @patch("apps.mail.admin.inbox.services.list_inbox_messages")
    def test_inbox_fragment_refused_to_members_allowed_for_admins(self, mock_list):
        mock_list.return_value = []
        url = reverse("admin:mail_inbox_fragment")
        # Denied before the inbox service is touched.
        self.assert_refused_to_member(url)
        mock_list.assert_not_called()
        self.assert_allowed_for_admin(url)

    @patch("apps.mail.admin.inbox.services.fetch_inbox_message")
    def test_inbox_detail_refused_to_members(self, mock_fetch):
        url = reverse("admin:mail_inbox_detail", args=["42"])
        self.assert_refused_to_member(url)
        mock_fetch.assert_not_called()

    @patch("apps.mail.admin.inbox.services.fetch_inbox_message")
    def test_inbox_detail_fragment_refused_to_members(self, mock_fetch):
        url = reverse("admin:mail_inbox_detail_fragment", args=["42"])
        self.assert_refused_to_member(url)
        mock_fetch.assert_not_called()

    @patch("apps.mail.admin.inbox.services.fetch_inbox_message")
    def test_inbox_reply_get_refused_to_members(self, mock_fetch):
        url = reverse("admin:mail_inbox_reply", args=["42"])
        self.assert_refused_to_member(url)
        mock_fetch.assert_not_called()

    @patch("apps.mail.admin.inbox.services.send_reply")
    @patch("apps.mail.admin.inbox.services.fetch_inbox_message")
    def test_inbox_reply_post_refused_to_members(self, mock_fetch, mock_send):
        url = reverse("admin:mail_inbox_reply", args=["42"])
        self.assert_refused_to_member(url, method="post", data={"reply_body": "hi", "to_email": "x@example.com"})
        mock_send.assert_not_called()

    @patch("apps.mail.admin.inbox.services.send_reply")
    @patch("apps.mail.admin.inbox.services.fetch_inbox_message")
    def test_inbox_reply_fragment_post_refused_to_members(self, mock_fetch, mock_send):
        url = reverse("admin:mail_inbox_reply_fragment", args=["42"])
        self.assert_refused_to_member(url, method="post", data={"reply_body": "hi", "to_email": "x@example.com"})
        mock_send.assert_not_called()

    @patch("apps.mail.admin.inbox.services.fetch_inbox_message")
    def test_inbox_detail_allowed_for_admins(self, mock_fetch):
        mock_fetch.return_value = {
            "uid": "42",
            "from_name": "Alice",
            "from_email": "alice@example.com",
            "to": [],
            "cc": [],
            "subject": "Hi",
            "snippet": "Body",
            "date": "2026-01-01",
            "is_seen": True,
            "html": "<p>Hello</p>",
            "text": "Hello",
            "message_id": "<m@example.com>",
            "references": "",
        }
        url = reverse("admin:mail_inbox_detail", args=["42"])
        self.assert_allowed_for_admin(url)
