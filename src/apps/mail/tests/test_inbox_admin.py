from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.mail.services.inbox.reply import send_reply
from core.models import AWSCredentialConfig, EmailServiceConfig
from event.tests.helpers import make_superuser


class InboxAdminFragmentTest(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")

    @patch("apps.mail.admin.inbox.list_inbox_messages")
    def test_inbox_fragment_force_refreshes_and_returns_html(self, mock_list):
        mock_list.return_value = [
            {
                "uid": "42",
                "from_name": "A",
                "from_email": "a@example.com",
                "subject": "Hi",
                "snippet": "Body",
                "date": "2026-01-01",
                "is_seen": True,
            }
        ]

        response = self.client.get(reverse("admin:mail_inbox_fragment") + "?refresh=1")

        self.assertEqual(response.status_code, 200)
        mock_list.assert_called_once_with(limit=30, force_refresh=True)
        self.assertIn(b"Hi", response.content)
        self.assertIn(b"data-inbox-refresh", response.content)

    @patch("apps.mail.admin.inbox.list_inbox_messages")
    def test_inbox_fragment_uses_cache_without_refresh_param(self, mock_list):
        mock_list.return_value = []

        response = self.client.get(reverse("admin:mail_inbox_fragment"))

        self.assertEqual(response.status_code, 200)
        mock_list.assert_called_once_with(limit=30, force_refresh=False)

    def _plain_text_message(self):
        return {
            "uid": "42",
            "from_name": "Attacker",
            "from_email": "attacker@example.com",
            "to": [],
            "cc": [],
            "subject": "Plain text fallback",
            "snippet": "Body",
            "date": "2026-01-01",
            "is_seen": True,
            "html": "",
            "text": "</pre><script>alert('xss')</script>",
            "message_id": "<msg@example.com>",
            "references": "",
        }

    @patch("apps.mail.admin.inbox.analyze_email")
    @patch("apps.mail.admin.inbox.fetch_inbox_message")
    def test_detail_escapes_plain_text_body_fallback(self, mock_fetch, mock_analyze):
        mock_fetch.return_value = self._plain_text_message()
        mock_analyze.return_value = {
            "risk_level": "low",
            "score": 0,
            "score_percent": 0,
            "reasons": [],
            "findings": [],
            "summary": "",
            "recommendation": "",
            "link_warnings": [],
        }

        response = self.client.get(reverse("admin:mail_inbox_detail", args=["42"]))

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"\\u0026lt;/pre\\u0026gt;", response.content)
        self.assertNotIn(b"</pre><script>alert", response.content)
        self.assertNotIn(b"<script>alert", response.content)

    @patch("apps.mail.admin.inbox.analyze_email")
    @patch("apps.mail.admin.inbox.fetch_inbox_message")
    def test_detail_fragment_escapes_plain_text_body_fallback(self, mock_fetch, mock_analyze):
        mock_fetch.return_value = self._plain_text_message()
        mock_analyze.return_value = {
            "risk_level": "low",
            "score": 0,
            "score_percent": 0,
            "reasons": [],
            "findings": [],
            "summary": "",
            "recommendation": "",
            "link_warnings": [],
        }

        response = self.client.get(reverse("admin:mail_inbox_detail_fragment", args=["42"]))

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"\\u0026lt;/pre\\u0026gt;", response.content)
        self.assertNotIn(b"</pre><script>alert", response.content)
        self.assertNotIn(b"<script>alert", response.content)

    @patch("apps.mail.admin.inbox.fetch_inbox_message")
    def test_detail_fragment_renders_security_analysis_panel(self, mock_fetch):
        message = self._plain_text_message()
        message["text"] = ""
        message["html"] = '<a href="https://evil.example/login">ucmerced.edu</a>'
        mock_fetch.return_value = message

        response = self.client.get(reverse("admin:mail_inbox_detail_fragment", args=["42"]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-scam-analysis-panel")
        self.assertContains(response, "Security analysis")
        self.assertContains(response, "Link check")
        self.assertContains(response, "ucmerced.edu")
        self.assertContains(response, "evil.example")


class InboxReplySendSettingsTest(TestCase):
    def setUp(self):
        EmailServiceConfig.objects.create(
            name="Mail",
            is_active=True,
            ses_from_email="reply@example.com",
            ses_from_name="I2G",
        )

    def test_reply_requires_ses_when_aws_is_not_configured(self):
        error = send_reply(
            to_email="recipient@example.com",
            subject="Re: Hi",
            reply_body="Hello",
            cc_email="copy@example.com",
        )

        self.assertIn("Email delivery is not configured", error)

    @patch("boto3.client")
    def test_reply_returns_error_when_ses_send_fails(self, mock_boto_client):
        AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="AKID",
            secret_access_key="SECRET",
            default_region="us-west-2",
        )
        mock_boto_client.return_value.send_raw_email.side_effect = RuntimeError("SES failed")

        error = send_reply(
            to_email="recipient@example.com",
            subject="Re: Hi",
            reply_body="Hello",
        )

        self.assertIn("Failed to send reply", error)
        mock_boto_client.return_value.send_raw_email.assert_called_once()
