from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from event.tests.helpers import make_superuser


class InboxAdminFragmentTest(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")

    @patch("mail.admin.inbox.list_inbox_messages")
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

    @patch("mail.admin.inbox.list_inbox_messages")
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

    @patch("mail.admin.inbox.analyze_email")
    @patch("mail.admin.inbox.fetch_inbox_message")
    def test_detail_escapes_plain_text_body_fallback(self, mock_fetch, mock_analyze):
        mock_fetch.return_value = self._plain_text_message()
        mock_analyze.return_value = {"risk_level": "low", "score": 0, "reasons": []}

        response = self.client.get(reverse("admin:mail_inbox_detail", args=["42"]))

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"&lt;/pre&gt;&lt;script&gt;alert", response.content)
        self.assertNotIn(b"</pre><script>alert", response.content)

    @patch("mail.admin.inbox.analyze_email")
    @patch("mail.admin.inbox.fetch_inbox_message")
    def test_detail_fragment_escapes_plain_text_body_fallback(self, mock_fetch, mock_analyze):
        mock_fetch.return_value = self._plain_text_message()
        mock_analyze.return_value = {"risk_level": "low", "score": 0, "reasons": []}

        response = self.client.get(reverse("admin:mail_inbox_detail_fragment", args=["42"]))

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"&lt;/pre&gt;&lt;script&gt;alert", response.content)
        self.assertNotIn(b"</pre><script>alert", response.content)
