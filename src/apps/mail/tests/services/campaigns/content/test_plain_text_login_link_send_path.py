from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.core.models import EmailServiceConfig
from apps.event.tests.helpers import make_member
from apps.mail.models import EmailCampaign, LoginLinkToken, RecipientLog
from apps.mail.services.campaign.send.runner import _send_one_recipient
from apps.mail.services.campaign.send.transport import SesSendResult
from apps.mail.tests.services.campaigns.content.test_campaign_autolink import _hrefs


@override_settings(FRONTEND_URL="https://i2g.example")
class PlainTextLoginLinkSendPathTests(TestCase):
    """Render a real plain-text campaign body through the send path (only the provider is mocked)."""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.client = APIClient()
        self.config = EmailServiceConfig.objects.create(
            is_active=True,
            from_email="noreply@example.com",
            from_name="Test",
            max_send_rate=0,
        )
        self.member = make_member(email="reader@example.com", first_name="Rita", last_name="Reader")
        self.recipient = {
            "member_id": self.member.pk,
            "email": "reader@example.com",
            "full_name": "Rita Reader",
            "first_name": "Rita",
            "last_name": "Reader",
        }

    def _send(self, body):
        campaign = EmailCampaign.objects.create(
            subject="Sign in",
            body=body,
            audience_type="subscribers",
            member_email_scope="primary",
            status="sending",
            include_unsubscribe_header=False,
        )
        with patch("apps.mail.services.campaign.send.runner._send_via_ses") as mock_send:
            mock_send.return_value = SesSendResult(message_id="SES-001")
            _send_one_recipient(campaign, self.config, MagicMock(), "", self.recipient)
        log = RecipientLog.objects.get(campaign=campaign, email_address="reader@example.com")
        self.assertEqual(log.status, "sent", log.error_message)
        mock_send.assert_called_once()
        return campaign, mock_send.call_args.kwargs["html_body"]

    def test_login_link_followed_by_punctuation_still_logs_in(self):
        for body in [
            "Sign in here: {{login_link}}.",
            "({{login_link}})",
            "Sign in here: {{login_link}},",
            "Click {{login_link}}!",
            "Sign in here: {{ login_link }}.",
            "登录链接：{{login_link}}。",
            "（{{login_link}}）",
            "登录链接：{{login_link}}，请继续",
        ]:
            with self.subTest(body=body):
                campaign, html = self._send(body)

                hrefs = [href for href in _hrefs(html) if "/login-link#token=" in href]
                self.assertEqual(len(hrefs), 1)
                token = hrefs[0].split("#token=", 1)[1]
                self.assertEqual(len(token), 64)
                link = LoginLinkToken.objects.get(token=token)
                self.assertEqual(link.campaign, campaign)
                self.assertFalse(link.is_used)

                response = self.client.post("/mail/login-link/", {"token": token}, format="json")

                self.assertEqual(response.status_code, 200, response.data)
                self.assertIn("access", response.data)
                link.refresh_from_db()
                self.assertTrue(link.is_used)
