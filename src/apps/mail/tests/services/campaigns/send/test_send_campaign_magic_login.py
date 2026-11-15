from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.core.models import EmailServiceConfig
from apps.event.tests.helpers import make_member
from apps.mail.models import EmailCampaign, LoginLinkToken
from apps.mail.services.campaign.send.runner import send_campaign
from apps.mail.services.campaign.send.transport import SesSendResult
from apps.mail.tests.services.campaigns.send.test_send_campaign_runner import _make_active_aws


class SendCampaignMagicLoginTests(TestCase):
    def setUp(self):
        self.aws = _make_active_aws()
        self.config = EmailServiceConfig.objects.create(
            is_active=True,
            from_email="noreply@example.com",
            from_name="Test",
            max_send_rate=0,
        )
        self.m1 = make_member(email="member@example.com", first_name="Member", last_name="One")
        self.sender = make_member(email="sender@example.com", first_name="Sender", last_name="S")
        self.campaign = EmailCampaign.objects.create(
            subject="Link",
            body="<p>Click here</p>",
            audience_type="subscribers",
            member_email_scope="primary",
            status="draft",
        )

    @patch("apps.mail.services.campaign.send.runner._send_via_ses")
    @patch("apps.mail.services.campaign.send.runner._get_ses_client")
    def test_login_link_token_created_per_member(self, mock_client, mock_send):
        mock_client.return_value = MagicMock()
        mock_send.return_value = SesSendResult(message_id="SES-001")
        send_campaign(self.campaign, self.sender)
        tokens = LoginLinkToken.objects.filter(campaign=self.campaign, member=self.m1)
        self.assertEqual(tokens.count(), 1)

    @patch("apps.mail.services.campaign.send.runner._send_via_ses")
    @patch("apps.mail.services.campaign.send.runner._get_ses_client")
    def test_login_link_validity_frozen_from_campaign(self, mock_client, mock_send):
        from datetime import timedelta

        from django.utils import timezone

        mock_client.return_value = MagicMock()
        mock_send.return_value = SesSendResult(message_id="SES-001")
        self.campaign.login_link_validity_days = 30
        self.campaign.save(update_fields=["login_link_validity_days", "updated_at"])

        before = timezone.now() + timedelta(days=30)
        send_campaign(self.campaign, self.sender)
        after = timezone.now() + timedelta(days=30)

        token = LoginLinkToken.objects.get(campaign=self.campaign, member=self.m1)
        self.assertGreaterEqual(token.expires_at, before)
        self.assertLessEqual(token.expires_at, after)

    @patch("apps.mail.services.campaign.send.runner._send_via_ses")
    @patch("apps.mail.services.campaign.send.runner._get_ses_client")
    def test_no_token_for_manual_emails_without_member(self, mock_client, mock_send):
        mock_client.return_value = MagicMock()
        mock_send.return_value = SesSendResult(message_id="SES-001")
        self.campaign.audience_type = "manual"
        self.campaign.manual_emails = "random@test.com"
        self.campaign.save()
        send_campaign(self.campaign, self.sender)
        self.assertEqual(LoginLinkToken.objects.filter(campaign=self.campaign).count(), 0)
