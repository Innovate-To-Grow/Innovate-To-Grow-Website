"""Per-Django-app authorization gating for the mail app's custom admin views.

Custom admin URLs registered through ``admin_view(...)`` are gated only by
is_staff/is_active — Django does NOT run the per-app permission model for them.
The per-app model lives in ``apps.core.access.user_can_access_app`` and the
``BaseModelAdmin`` permission methods. Without an explicit re-check, a staff
member whose ``Member.admin_apps`` lacks the ``mail`` app could still hit these
URLs and read data or trigger privileged sends.

These tests exercise the real Django admin through the test client:
  * a staff member WITHOUT the ``mail`` app gets HTTP 403 (the view's
    ``PermissionDenied`` is rendered as a 403 response by the test client), and
  * a superuser (who bypasses the per-app list) is allowed (not 403).
"""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.core.models import AWSCredentialConfig, EmailServiceConfig
from apps.event.tests.helpers import make_admin, make_superuser
from apps.mail.models import EmailCampaign, SmsCampaign


def _make_delivery_configs():
    AWSCredentialConfig.objects.all().delete()
    AWSCredentialConfig.objects.create(
        name="AWS",
        is_active=True,
        access_key_id="AKIATEST",
        secret_access_key="secret",
        default_region="us-west-2",
    )
    EmailServiceConfig.objects.all().delete()
    return EmailServiceConfig.objects.create(
        name="SES",
        is_active=True,
        ses_from_email="test@ucmerced.edu",
        ses_from_name="Test",
    )


class MailAdminAuthzTestBase(TestCase):
    """Shared setup: a grant-less staff member and a superuser."""

    def setUp(self):
        cache.clear()
        # Staff member whose admin_apps does NOT include "mail".
        self.nogrant = make_admin(apps=["event"], email="nomail@example.com")
        self.superuser = make_superuser(email="master@example.com")
        _make_delivery_configs()

    def tearDown(self):
        cache.clear()

    def assert_denied_for_grantless(self, url, method="get", **kwargs):
        self.client.force_login(self.nogrant)
        response = getattr(self.client, method)(url, **kwargs)
        self.assertEqual(
            response.status_code,
            403,
            f"grant-less staff should be 403 on {url} ({method}), got {response.status_code}",
        )

    def assert_allowed_for_superuser(self, url, method="get", **kwargs):
        self.client.force_login(self.superuser)
        response = getattr(self.client, method)(url, **kwargs)
        self.assertNotEqual(
            response.status_code,
            403,
            f"superuser should not be 403 on {url} ({method}), got {response.status_code}",
        )
        return response


class SmsCampaignAdminAuthzTest(MailAdminAuthzTestBase):
    def setUp(self):
        super().setUp()
        self.campaign = SmsCampaign.objects.create(
            name="Blast",
            message="Hello {{ first_name }}",
            audience_type="manual",
            manual_phones="+12345678901",
            status="draft",
        )

    def test_preview_recipients_denied_for_grantless_allowed_for_superuser(self):
        url = reverse("admin:mail_smscampaign_preview_recipients", args=[self.campaign.pk])
        self.assert_denied_for_grantless(url)
        self.assert_allowed_for_superuser(url)

    def test_send_preview_denied_for_grantless_allowed_for_superuser(self):
        url = reverse("admin:mail_smscampaign_send_preview", args=[self.campaign.pk])
        self.assert_denied_for_grantless(url)
        self.assert_allowed_for_superuser(url)

    def test_send_confirm_get_denied_for_grantless_allowed_for_superuser(self):
        url = reverse("admin:mail_smscampaign_send_confirm", args=[self.campaign.pk])
        self.assert_denied_for_grantless(url)
        self.assert_allowed_for_superuser(url)

    def test_send_confirm_post_denied_for_grantless(self):
        # State-changing POST must be blocked before it can flip the campaign to "sending".
        url = reverse("admin:mail_smscampaign_send_confirm", args=[self.campaign.pk])
        self.assert_denied_for_grantless(url, method="post", data={"confirmation_text": self.campaign.name})
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, "draft")

    def test_send_status_denied_for_grantless_allowed_for_superuser(self):
        url = reverse("admin:mail_smscampaign_send_status", args=[self.campaign.pk])
        self.assert_denied_for_grantless(url)
        self.assert_allowed_for_superuser(url)

    def test_send_status_json_denied_for_grantless_allowed_for_superuser(self):
        url = reverse("admin:mail_smscampaign_send_status_json", args=[self.campaign.pk])
        self.assert_denied_for_grantless(url)
        response = self.assert_allowed_for_superuser(url)
        self.assertEqual(response.status_code, 200)


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

    def test_preview_recipients_denied_for_grantless_allowed_for_superuser(self):
        url = reverse("admin:mail_emailcampaign_preview_recipients", args=[self.campaign.pk])
        self.assert_denied_for_grantless(url)
        self.assert_allowed_for_superuser(url)

    def test_send_preview_denied_for_grantless_allowed_for_superuser(self):
        url = reverse("admin:mail_emailcampaign_send_preview", args=[self.campaign.pk])
        self.assert_denied_for_grantless(url)
        self.assert_allowed_for_superuser(url)

    def test_send_confirm_get_denied_for_grantless_allowed_for_superuser(self):
        url = reverse("admin:mail_emailcampaign_send_confirm", args=[self.campaign.pk])
        self.assert_denied_for_grantless(url)
        self.assert_allowed_for_superuser(url)

    def test_send_confirm_post_denied_for_grantless(self):
        url = reverse("admin:mail_emailcampaign_send_confirm", args=[self.campaign.pk])
        self.assert_denied_for_grantless(url, method="post", data={"confirmation_text": self.campaign.name})
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, "draft")

    def test_status_denied_for_grantless_allowed_for_superuser(self):
        url = reverse("admin:mail_emailcampaign_send_status", args=[self.campaign.pk])
        self.assert_denied_for_grantless(url)
        self.assert_allowed_for_superuser(url)

    def test_status_json_denied_for_grantless_allowed_for_superuser(self):
        url = reverse("admin:mail_emailcampaign_send_status_json", args=[self.campaign.pk])
        self.assert_denied_for_grantless(url)
        response = self.assert_allowed_for_superuser(url)
        self.assertEqual(response.status_code, 200)

    def test_inline_preview_denied_for_grantless(self):
        url = reverse("admin:mail_emailcampaign_inline_preview")
        self.assert_denied_for_grantless(url, method="post", data={"body": "hi", "body_format": "plain"})

    def test_inline_preview_allowed_for_superuser(self):
        url = reverse("admin:mail_emailcampaign_inline_preview")
        response = self.assert_allowed_for_superuser(url, method="post", data={"body": "hi", "body_format": "plain"})
        self.assertEqual(response.status_code, 200)

    @patch("apps.mail.admin.campaign.list_recent_sent_messages")
    @patch("apps.mail.admin.campaign.resolve_gmail_mailbox")
    def test_import_gmail_html_denied_for_grantless_allowed_for_superuser(self, mock_mailbox, mock_list):
        mock_mailbox.return_value = "inbox@example.com"
        mock_list.return_value = []
        url = reverse("admin:mail_emailcampaign_import_gmail_html", args=[self.campaign.pk])
        # Denied before any Gmail service call.
        self.assert_denied_for_grantless(url)
        mock_list.assert_not_called()
        self.assert_allowed_for_superuser(url)

    def test_import_gmail_html_confirm_denied_for_grantless(self):
        url = reverse("admin:mail_emailcampaign_import_gmail_html_confirm", args=[self.campaign.pk])
        self.assert_denied_for_grantless(url, method="post", data={"message_id": "abc"})


class InboxAdminAuthzTest(MailAdminAuthzTestBase):
    def test_inbox_list_denied_for_grantless_allowed_for_superuser(self):
        url = reverse("admin:mail_inbox_list")
        self.assert_denied_for_grantless(url)
        self.assert_allowed_for_superuser(url)

    @patch("apps.mail.admin.inbox.list_inbox_messages")
    def test_inbox_fragment_denied_for_grantless_allowed_for_superuser(self, mock_list):
        mock_list.return_value = []
        url = reverse("admin:mail_inbox_fragment")
        # Denied before the inbox service is touched.
        self.assert_denied_for_grantless(url)
        mock_list.assert_not_called()
        self.assert_allowed_for_superuser(url)

    @patch("apps.mail.admin.inbox.fetch_inbox_message")
    def test_inbox_detail_denied_for_grantless(self, mock_fetch):
        url = reverse("admin:mail_inbox_detail", args=["42"])
        self.assert_denied_for_grantless(url)
        mock_fetch.assert_not_called()

    @patch("apps.mail.admin.inbox.fetch_inbox_message")
    def test_inbox_detail_fragment_denied_for_grantless(self, mock_fetch):
        url = reverse("admin:mail_inbox_detail_fragment", args=["42"])
        self.assert_denied_for_grantless(url)
        mock_fetch.assert_not_called()

    @patch("apps.mail.admin.inbox.fetch_inbox_message")
    def test_inbox_reply_get_denied_for_grantless(self, mock_fetch):
        url = reverse("admin:mail_inbox_reply", args=["42"])
        self.assert_denied_for_grantless(url)
        mock_fetch.assert_not_called()

    @patch("apps.mail.admin.inbox.send_reply")
    @patch("apps.mail.admin.inbox.fetch_inbox_message")
    def test_inbox_reply_post_denied_for_grantless(self, mock_fetch, mock_send):
        url = reverse("admin:mail_inbox_reply", args=["42"])
        self.assert_denied_for_grantless(url, method="post", data={"reply_body": "hi", "to_email": "x@example.com"})
        mock_send.assert_not_called()

    @patch("apps.mail.admin.inbox.send_reply")
    @patch("apps.mail.admin.inbox.fetch_inbox_message")
    def test_inbox_reply_fragment_post_denied_for_grantless(self, mock_fetch, mock_send):
        url = reverse("admin:mail_inbox_reply_fragment", args=["42"])
        self.assert_denied_for_grantless(url, method="post", data={"reply_body": "hi", "to_email": "x@example.com"})
        mock_send.assert_not_called()

    @patch("apps.mail.admin.inbox.fetch_inbox_message")
    def test_inbox_detail_allowed_for_superuser(self, mock_fetch):
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
        self.assert_allowed_for_superuser(url)


class MailSettingsAdminAuthzTest(MailAdminAuthzTestBase):
    def test_settings_view_denied_for_grantless_allowed_for_superuser(self):
        url = reverse("admin:mail_settings")
        self.assert_denied_for_grantless(url)
        self.assert_allowed_for_superuser(url)

    def test_settings_edit_denied_for_grantless_allowed_for_superuser(self):
        url = reverse("admin:mail_settings_edit")
        self.assert_denied_for_grantless(url)
        self.assert_allowed_for_superuser(url)

    def test_settings_edit_post_denied_for_grantless(self):
        url = reverse("admin:mail_settings_edit")
        self.assert_denied_for_grantless(url, method="post", data={})

    @patch("apps.mail.admin.settings._send_test_email")
    def test_test_email_get_denied_for_grantless_allowed_for_superuser(self, mock_send):
        url = reverse("admin:mail_settings_test_email")
        self.assert_denied_for_grantless(url)
        self.assert_allowed_for_superuser(url)

    @patch("apps.mail.admin.settings._send_test_email")
    def test_test_email_post_denied_for_grantless(self, mock_send):
        url = reverse("admin:mail_settings_test_email")
        self.assert_denied_for_grantless(url, method="post", data={"recipient": "x@example.com"})
        mock_send.assert_not_called()

    @patch("apps.mail.admin.settings._send_test_sms")
    def test_test_sms_get_denied_for_grantless_allowed_for_superuser(self, mock_send):
        url = reverse("admin:mail_settings_test_sms")
        self.assert_denied_for_grantless(url)
        self.assert_allowed_for_superuser(url)

    @patch("apps.mail.admin.settings._send_test_sms")
    def test_test_sms_post_denied_for_grantless(self, mock_send):
        url = reverse("admin:mail_settings_test_sms")
        self.assert_denied_for_grantless(url, method="post", data={"recipient": "2345678901", "country_code": "+1"})
        mock_send.assert_not_called()
