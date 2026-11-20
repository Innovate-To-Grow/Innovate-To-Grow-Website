from unittest.mock import patch

from django.urls import reverse

from apps.mail.tests.admin.inbox.test_inbox_admin import _InboxAdminFragmentCase


class InboxAdminFragmentTest(_InboxAdminFragmentCase):
    @patch("apps.mail.admin.inbox.services.fetch_inbox_message")
    def test_detail_fragment_inbox_folder_shows_reply(self, mock_fetch):
        mock_fetch.return_value = self._benign_message()

        response = self.client.get(reverse("admin:mail_inbox_detail_fragment", args=["42"]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-inbox-reply-link")

    @patch("apps.mail.admin.inbox.services.fetch_inbox_message")
    def test_detail_fragment_sent_folder_hides_reply(self, mock_fetch):
        mock_fetch.return_value = self._benign_message()

        response = self.client.get(reverse("admin:mail_inbox_detail_fragment", args=["42"]) + "?folder=SENT")

        self.assertEqual(response.status_code, 200)
        mock_fetch.assert_called_once_with("42", folder="SENT", account="")
        self.assertNotContains(response, "data-inbox-reply-link")

    @patch("apps.mail.admin.inbox.services.assess_email")
    @patch("apps.mail.admin.inbox.services.fetch_inbox_message")
    def test_detail_fragment_renders_ai_review_section(self, mock_fetch, mock_assess):
        mock_fetch.return_value = self._benign_message()
        mock_assess.return_value = {
            "risk_level": "high",
            "score": 4,
            "score_percent": 90,
            "reasons": ["Reply-To domain differs"],
            "findings": [],
            "summary": "AI review flagged this message as a likely scam.",
            "recommendation": "Do not act on this message.",
            "link_warnings": [],
            "ai_review": {
                "verdict": "scam",
                "confidence": 0.95,
                "risk_score": 96,
                "reasons": ["Sender domain was registered yesterday"],
            },
        }

        response = self.client.get(reverse("admin:mail_inbox_detail_fragment", args=["42"]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AI review")
        self.assertContains(response, "Sender domain was registered yesterday")
