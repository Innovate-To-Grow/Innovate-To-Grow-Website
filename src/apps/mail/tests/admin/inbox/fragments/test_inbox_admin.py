from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.event.tests.helpers import make_superuser
from apps.mail.services.inbox import InboxListing


class _InboxAdminFragmentCase(TestCase):
    def setUp(self):
        # The inbox account and sender lists are cached per container.
        cache.clear()
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")

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

    def _benign_message(self):
        message = self._plain_text_message()
        message["from_name"] = "Pat Lee"
        message["from_email"] = "pat@example.com"
        message["text"] = "Hello team, see you at the Monday standup."
        message["html"] = "<p>Hello team, see you at the Monday standup.</p>"
        return message


class InboxAdminFragmentTest(_InboxAdminFragmentCase):
    @patch("apps.mail.admin.inbox.services.list_all_inbox_messages")
    def test_inbox_fragment_force_refreshes_and_returns_html(self, mock_list):
        mock_list.return_value = InboxListing(
            messages=[
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
        )

        response = self.client.get(reverse("admin:mail_inbox_fragment") + "?refresh=1")

        self.assertEqual(response.status_code, 200)
        mock_list.assert_called_once_with(limit=30, force_refresh=True, folder="INBOX")
        self.assertIn(b"i2g-mail-shell", response.content)
        self.assertIn(b"data-inbox-account-toggle", response.content)
        self.assertIn(b"data-inbox-account-panel", response.content)
        self.assertIn(b"data-inbox-list-toggle", response.content)
        self.assertIn(b"Hi", response.content)
        self.assertIn(b"data-inbox-refresh", response.content)

    @patch("apps.mail.admin.inbox.services.list_all_inbox_messages")
    def test_inbox_fragment_uses_cache_without_refresh_param(self, mock_list):
        mock_list.return_value = InboxListing()

        response = self.client.get(reverse("admin:mail_inbox_fragment"))

        self.assertEqual(response.status_code, 200)
        mock_list.assert_called_once_with(limit=30, force_refresh=False, folder="INBOX")

    @patch("apps.mail.admin.inbox.services.list_all_inbox_messages")
    def test_inbox_fragment_sent_folder_lists_recipients(self, mock_list):
        mock_list.return_value = InboxListing(
            messages=[
                {
                    "uid": "7",
                    "from_name": "Me",
                    "from_email": "me@example.com",
                    "to": [{"name": "Bob Recipient", "email": "bob@example.com"}],
                    "subject": "Sent hello",
                    "snippet": "Body",
                    "date": "2026-01-01",
                    "is_seen": True,
                }
            ]
        )

        response = self.client.get(reverse("admin:mail_inbox_fragment") + "?folder=SENT&refresh=1")

        self.assertEqual(response.status_code, 200)
        mock_list.assert_called_once_with(limit=30, force_refresh=True, folder="SENT")
        self.assertIn(b'data-inbox-folder="SENT"', response.content)
        # Sent rows show the recipient rather than the sender.
        self.assertIn(b"Bob Recipient", response.content)

    @patch("apps.mail.admin.inbox.services.analyze_email")
    @patch("apps.mail.admin.inbox.services.fetch_inbox_message")
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

    @patch("apps.mail.admin.inbox.services.analyze_email")
    @patch("apps.mail.admin.inbox.services.fetch_inbox_message")
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

    @patch("apps.mail.admin.inbox.services.fetch_inbox_message")
    def test_detail_fragment_renders_security_analysis_panel(self, mock_fetch):
        message = self._plain_text_message()
        message["text"] = ""
        message["html"] = '<a href="https://evil.example/login">ucmerced.edu</a>'
        mock_fetch.return_value = message

        response = self.client.get(reverse("admin:mail_inbox_detail_fragment", args=["42"]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-scam-analysis-panel")
        self.assertContains(response, "data-inbox-body-frame")
        self.assertContains(response, 'scrolling="no"')
        self.assertContains(response, "i2g-scam-panel")
        self.assertContains(response, 'data-risk-level="medium"')
        self.assertContains(response, "Security analysis")
        self.assertContains(response, "Link check")
        self.assertContains(response, "ucmerced.edu")
        self.assertContains(response, "evil.example")
        self.assertNotContains(response, "SECURITY: this iframe renders")

    @patch("apps.mail.admin.inbox.services.fetch_inbox_message")
    def test_detail_fragment_low_risk_shows_calm_panel(self, mock_fetch):
        mock_fetch.return_value = self._benign_message()

        response = self.client.get(reverse("admin:mail_inbox_detail_fragment", args=["42"]))

        self.assertEqual(response.status_code, 200)
        mock_fetch.assert_called_once_with("42", folder="INBOX", account="")
        self.assertContains(response, 'data-risk-level="low"')
        self.assertContains(response, "No suspicious signals detected.")
        self.assertContains(response, "Security analysis")
        self.assertNotContains(response, "Review this message before clicking")
