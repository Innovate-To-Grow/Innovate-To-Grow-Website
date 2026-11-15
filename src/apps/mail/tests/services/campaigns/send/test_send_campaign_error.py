from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.core.models import EmailServiceConfig
from apps.event.tests.helpers import make_member
from apps.mail.models import EmailCampaign, RecipientLog
from apps.mail.services.campaign.send.runner import send_campaign
from apps.mail.services.campaign.send.transport import SesSendResult
from apps.mail.tests.services.campaigns.send.test_send_campaign_runner import _make_active_aws


class SendCampaignErrorTests(TestCase):
    def setUp(self):
        self.m1 = make_member(email="err@example.com", first_name="Err", last_name="Test")
        self.sender = make_member(email="sender@example.com", first_name="Sender", last_name="S")
        self.campaign = EmailCampaign.objects.create(
            subject="Fail",
            body="<p>oops</p>",
            audience_type="subscribers",
            member_email_scope="primary",
            status="draft",
        )

    @patch("apps.mail.services.campaign.send.runner.get_recipients", return_value=[])
    @patch("apps.mail.services.campaign.send.runner.EmailServiceConfig.load")
    @patch("apps.mail.services.campaign.send.runner._get_ses_client")
    def test_fallback_campaign_with_no_recipients_is_sent(self, get_ses_client, load_config, _recipients):
        result = send_campaign(self.campaign, self.sender)

        self.campaign.refresh_from_db()
        self.assertEqual(result, {"total": 0, "sent": 0, "failed": 0})
        self.assertEqual(self.campaign.status, "sent")
        self.assertIsNotNone(self.campaign.sent_at)
        load_config.assert_not_called()
        get_ses_client.assert_not_called()

    def test_missing_delivery_config_fails_campaign(self):
        with self.assertRaises(RuntimeError):
            send_campaign(self.campaign, self.sender)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, "failed")
        self.assertIn("Email delivery is not configured", self.campaign.error_message)
        logs = RecipientLog.objects.filter(campaign=self.campaign)
        self.assertGreater(logs.count(), 0)
        self.assertEqual(logs.exclude(status="failed").count(), 0)
        self.assertEqual(logs.exclude(provider="").count(), 0)

    @patch("apps.mail.services.campaign.send.runner._send_via_ses")
    @patch("apps.mail.services.campaign.send.runner._get_ses_client")
    def test_null_ses_client_fails_campaign(self, mock_client, mock_send):
        _make_active_aws()
        EmailServiceConfig.objects.create(
            is_active=True,
            max_send_rate=0,
        )
        mock_client.return_value = None
        with self.assertRaises(RuntimeError):
            send_campaign(self.campaign, self.sender)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, "failed")

    def test_email_config_without_aws_fails_without_fallback(self):
        EmailServiceConfig.objects.create(
            is_active=True,
            from_email="noreply@example.com",
            from_name="Test",
            max_send_rate=0,
        )
        with self.assertRaises(RuntimeError):
            send_campaign(self.campaign, self.sender)

        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, "failed")
        logs = RecipientLog.objects.filter(campaign=self.campaign)
        self.assertGreater(logs.count(), 0)
        self.assertEqual(logs.exclude(provider="").count(), 0)
        self.assertEqual(logs.exclude(status="failed").count(), 0)

    @patch("apps.mail.services.campaign.send.runner._send_via_ses")
    @patch("apps.mail.services.campaign.send.runner._get_ses_client")
    def test_ses_failure_records_failed_recipients_without_fallback(self, mock_client, mock_send_ses):
        _make_active_aws()
        EmailServiceConfig.objects.create(
            is_active=True,
            from_email="noreply@example.com",
            from_name="Test",
            max_send_rate=0,
        )
        mock_client.return_value = MagicMock()
        mock_send_ses.return_value = SesSendResult(error="SES throttled")

        send_campaign(self.campaign, self.sender)

        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, "failed")
        logs = RecipientLog.objects.filter(campaign=self.campaign)
        self.assertGreater(logs.count(), 0)
        self.assertEqual(logs.exclude(provider="ses").count(), 0)
        self.assertEqual(logs.exclude(status="failed").count(), 0)
        self.assertEqual(logs.exclude(provider_message_id="").count(), 0)

    @patch("apps.mail.services.campaign.send.runner._send_via_ses")
    @patch("apps.mail.services.campaign.send.runner._get_ses_client")
    def test_all_failures_increments_failed_count(self, mock_client, mock_send):
        _make_active_aws()
        EmailServiceConfig.objects.create(
            is_active=True,
            max_send_rate=0,
        )
        mock_client.return_value = MagicMock()
        mock_send.return_value = SesSendResult(error="SES throttled")
        send_campaign(self.campaign, self.sender)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.failed_count, self.campaign.total_recipients)
        self.assertEqual(self.campaign.status, "failed")

    @patch("apps.mail.services.campaign.send.runner._send_via_ses")
    @patch("apps.mail.services.campaign.send.runner._get_ses_client")
    def test_all_succeed_status_is_sent(self, mock_client, mock_send):
        _make_active_aws()
        EmailServiceConfig.objects.create(
            is_active=True,
            max_send_rate=0,
        )
        mock_client.return_value = MagicMock()
        mock_send.return_value = SesSendResult(message_id="OK-1")
        send_campaign(self.campaign, self.sender)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, "sent")
