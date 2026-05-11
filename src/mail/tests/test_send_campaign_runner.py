from unittest.mock import MagicMock, patch

from django.test import TestCase

from core.models import EmailServiceConfig
from event.tests.helpers import make_member
from mail.models import EmailCampaign, MagicLoginToken, RecipientLog
from mail.services.send_campaign.runner import SendTiming, send_campaign
from mail.services.send_campaign.transport import SesSendResult


class SendCampaignFlowTests(TestCase):
    def setUp(self):
        self.config = EmailServiceConfig.objects.create(
            is_active=True,
            ses_access_key_id="AKID",
            ses_secret_access_key="SECRET",
            ses_region="us-west-2",
            ses_from_email="noreply@example.com",
            ses_from_name="Test",
            ses_max_send_rate=0,
        )
        self.m1 = make_member(email="alice@example.com", first_name="Alice", last_name="Smith")
        self.m2 = make_member(email="bob@example.com", first_name="Bob", last_name="Jones")
        self.sender = make_member(email="admin@example.com", first_name="Admin", last_name="User")
        self.campaign = EmailCampaign.objects.create(
            subject="Hi {{first_name}}",
            body="<p>Hello</p>",
            audience_type="subscribers",
            member_email_scope="primary",
            status="draft",
        )

    @patch("mail.services.send_campaign.runner._send_via_ses")
    @patch("mail.services.send_campaign.runner._get_ses_client")
    def test_full_send_creates_recipient_logs(self, mock_client, mock_send):
        mock_client.return_value = MagicMock()
        mock_send.return_value = SesSendResult(message_id="SES-001")
        send_campaign(self.campaign, self.sender)
        self.assertEqual(RecipientLog.objects.filter(campaign=self.campaign).count(), 3)

    @patch("mail.services.send_campaign.runner._send_via_ses")
    @patch("mail.services.send_campaign.runner._get_ses_client")
    def test_campaign_status_transitions_to_sent(self, mock_client, mock_send):
        mock_client.return_value = MagicMock()
        mock_send.return_value = SesSendResult(message_id="SES-001")
        send_campaign(self.campaign, self.sender)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, "sent")

    @patch("mail.services.send_campaign.runner._send_via_ses")
    @patch("mail.services.send_campaign.runner._get_ses_client")
    def test_total_recipients_set_on_campaign(self, mock_client, mock_send):
        mock_client.return_value = MagicMock()
        mock_send.return_value = SesSendResult(message_id="SES-001")
        send_campaign(self.campaign, self.sender)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.total_recipients, 3)

    @patch("mail.services.send_campaign.runner._send_via_ses")
    @patch("mail.services.send_campaign.runner._get_ses_client")
    def test_sent_count_matches_successful_sends(self, mock_client, mock_send):
        mock_client.return_value = MagicMock()
        mock_send.return_value = SesSendResult(message_id="SES-001")
        send_campaign(self.campaign, self.sender)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.sent_count, 3)
        self.assertEqual(self.campaign.failed_count, 0)

    @patch("mail.services.send_campaign.runner._send_via_ses")
    @patch("mail.services.send_campaign.runner._get_ses_client")
    def test_sent_at_is_set_after_completion(self, mock_client, mock_send):
        mock_client.return_value = MagicMock()
        mock_send.return_value = SesSendResult(message_id="SES-001")
        send_campaign(self.campaign, self.sender)
        self.campaign.refresh_from_db()
        self.assertIsNotNone(self.campaign.sent_at)

    @patch("mail.services.send_campaign.runner._send_via_ses")
    @patch("mail.services.send_campaign.runner._get_ses_client")
    def test_recipient_log_records_ses_message_id(self, mock_client, mock_send):
        mock_client.return_value = MagicMock()
        mock_send.return_value = SesSendResult(message_id="SES-ABC-123")
        send_campaign(self.campaign, self.sender)
        log = RecipientLog.objects.filter(campaign=self.campaign).first()
        self.assertEqual(log.ses_message_id, "SES-ABC-123")
        self.assertEqual(log.status, "sent")


class SendCampaignMagicLoginTests(TestCase):
    def setUp(self):
        self.config = EmailServiceConfig.objects.create(
            is_active=True,
            ses_access_key_id="AKID",
            ses_secret_access_key="SECRET",
            ses_region="us-west-2",
            ses_from_email="noreply@example.com",
            ses_from_name="Test",
            ses_max_send_rate=0,
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

    @patch("mail.services.send_campaign.runner._send_via_ses")
    @patch("mail.services.send_campaign.runner._get_ses_client")
    def test_magic_login_token_created_per_member(self, mock_client, mock_send):
        mock_client.return_value = MagicMock()
        mock_send.return_value = SesSendResult(message_id="SES-001")
        send_campaign(self.campaign, self.sender)
        tokens = MagicLoginToken.objects.filter(campaign=self.campaign, member=self.m1)
        self.assertEqual(tokens.count(), 1)

    @patch("mail.services.send_campaign.runner._send_via_ses")
    @patch("mail.services.send_campaign.runner._get_ses_client")
    def test_no_token_for_manual_emails_without_member(self, mock_client, mock_send):
        mock_client.return_value = MagicMock()
        mock_send.return_value = SesSendResult(message_id="SES-001")
        self.campaign.audience_type = "manual"
        self.campaign.manual_emails = "random@test.com"
        self.campaign.save()
        send_campaign(self.campaign, self.sender)
        self.assertEqual(MagicLoginToken.objects.filter(campaign=self.campaign).count(), 0)


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

    def test_missing_ses_config_fails_campaign(self):
        with self.assertRaises(RuntimeError):
            send_campaign(self.campaign, self.sender)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, "failed")
        self.assertIn("SES is not configured", self.campaign.error_message)

    @patch("mail.services.send_campaign.runner._send_via_ses")
    @patch("mail.services.send_campaign.runner._get_ses_client")
    def test_null_ses_client_fails_campaign(self, mock_client, mock_send):
        EmailServiceConfig.objects.create(
            is_active=True,
            ses_access_key_id="AKID",
            ses_secret_access_key="SECRET",
            ses_max_send_rate=0,
        )
        mock_client.return_value = None
        with self.assertRaises(RuntimeError):
            send_campaign(self.campaign, self.sender)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, "failed")

    @patch("mail.services.send_campaign.runner._send_via_ses")
    @patch("mail.services.send_campaign.runner._get_ses_client")
    def test_all_failures_increments_failed_count(self, mock_client, mock_send):
        EmailServiceConfig.objects.create(
            is_active=True,
            ses_access_key_id="AKID",
            ses_secret_access_key="SECRET",
            ses_max_send_rate=0,
        )
        mock_client.return_value = MagicMock()
        mock_send.return_value = SesSendResult(error="SES throttled")
        send_campaign(self.campaign, self.sender)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.failed_count, self.campaign.total_recipients)
        self.assertEqual(self.campaign.status, "failed")

    @patch("mail.services.send_campaign.runner._send_via_ses")
    @patch("mail.services.send_campaign.runner._get_ses_client")
    def test_all_succeed_status_is_sent(self, mock_client, mock_send):
        EmailServiceConfig.objects.create(
            is_active=True,
            ses_access_key_id="AKID",
            ses_secret_access_key="SECRET",
            ses_max_send_rate=0,
        )
        mock_client.return_value = MagicMock()
        mock_send.return_value = SesSendResult(message_id="OK-1")
        send_campaign(self.campaign, self.sender)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, "sent")


class SendTimingTests(TestCase):
    def test_no_rate_limit_when_send_rate_zero(self):
        timing = SendTiming(0)
        self.assertEqual(timing.min_interval, 0)

    def test_min_interval_calculated_from_rate(self):
        timing = SendTiming(10)
        self.assertAlmostEqual(timing.min_interval, 0.1)

    def test_first_send_does_not_block(self):
        timing = SendTiming(10)
        timing.wait_if_needed()

    @patch("time.sleep")
    def test_sleep_when_sends_too_fast(self, mock_sleep):
        timing = SendTiming(1)
        timing.mark_sent()
        timing.wait_if_needed()
