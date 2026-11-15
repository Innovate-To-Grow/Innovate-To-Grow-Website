from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.core.models import AWSCredentialConfig, EmailServiceConfig
from apps.event.tests.helpers import make_member
from apps.mail.models import EmailCampaign, RecipientLog
from apps.mail.services.send_campaign.runner import send_campaign
from apps.mail.services.send_campaign.transport import SesSendResult


def _make_active_aws():
    AWSCredentialConfig.objects.all().delete()
    return AWSCredentialConfig.objects.create(
        name="AWS",
        is_active=True,
        access_key_id="AKID",
        secret_access_key="SECRET",
        default_region="us-west-2",
    )


class SendCampaignFlowTests(TestCase):
    def setUp(self):
        self.aws = _make_active_aws()
        self.config = EmailServiceConfig.objects.create(
            is_active=True,
            from_email="noreply@example.com",
            from_name="Test",
            max_send_rate=0,
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

    @patch("apps.mail.services.send_campaign.runner._send_via_ses")
    @patch("apps.mail.services.send_campaign.runner._get_ses_client")
    def test_full_send_creates_recipient_logs(self, mock_client, mock_send):
        mock_client.return_value = MagicMock()
        mock_send.return_value = SesSendResult(message_id="SES-001")
        send_campaign(self.campaign, self.sender)
        self.assertEqual(RecipientLog.objects.filter(campaign=self.campaign).count(), 3)

    @patch("apps.mail.services.send_campaign.runner._send_via_ses")
    @patch("apps.mail.services.send_campaign.runner._get_ses_client")
    def test_only_messages_that_carry_the_login_link_skip_the_sent_items_copy(self, mock_client, mock_send):
        mock_client.return_value = MagicMock()
        mock_send.return_value = SesSendResult(message_id="SES-001")
        send_campaign(self.campaign, self.sender)
        self.assertEqual({call.kwargs["keep_sent_copy"] for call in mock_send.call_args_list}, {True})

        mock_send.reset_mock()
        for subject, body in (("Hi", '<p><a href="{{ login_link }}">Sign in</a></p>'), ("{{login_link}}", "<p>x</p>")):
            campaign = EmailCampaign.objects.create(
                subject=subject, body=body, audience_type="subscribers", member_email_scope="primary", status="draft"
            )
            send_campaign(campaign, self.sender)
        self.assertEqual({call.kwargs["keep_sent_copy"] for call in mock_send.call_args_list}, {False})

    @patch("apps.mail.services.send_campaign.runner._send_via_ses")
    @patch("apps.mail.services.send_campaign.runner._get_ses_client")
    def test_campaign_status_transitions_to_sent(self, mock_client, mock_send):
        mock_client.return_value = MagicMock()
        mock_send.return_value = SesSendResult(message_id="SES-001")
        send_campaign(self.campaign, self.sender)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.status, "sent")

    @patch("apps.mail.services.send_campaign.runner._send_via_ses")
    @patch("apps.mail.services.send_campaign.runner._get_ses_client")
    def test_fallback_campaign_with_mixed_results_is_partial(self, mock_client, mock_send):
        mock_client.return_value = MagicMock()
        mock_send.side_effect = [
            SesSendResult(message_id="SES-001"),
            SesSendResult(error="SES rejected recipient"),
            SesSendResult(message_id="SES-003"),
        ]

        result = send_campaign(self.campaign, self.sender)

        self.campaign.refresh_from_db()
        self.assertEqual(result, {"total": 3, "sent": 2, "failed": 1})
        self.assertEqual(self.campaign.status, "partial")

    @patch("apps.mail.services.send_campaign.runner._send_via_ses")
    @patch("apps.mail.services.send_campaign.runner._get_ses_client")
    def test_total_recipients_set_on_campaign(self, mock_client, mock_send):
        mock_client.return_value = MagicMock()
        mock_send.return_value = SesSendResult(message_id="SES-001")
        send_campaign(self.campaign, self.sender)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.total_recipients, 3)

    @patch("apps.mail.services.send_campaign.runner._send_via_ses")
    @patch("apps.mail.services.send_campaign.runner._get_ses_client")
    def test_sent_count_matches_successful_sends(self, mock_client, mock_send):
        mock_client.return_value = MagicMock()
        mock_send.return_value = SesSendResult(message_id="SES-001")
        send_campaign(self.campaign, self.sender)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.sent_count, 3)
        self.assertEqual(self.campaign.failed_count, 0)

    @patch("apps.mail.services.send_campaign.runner._send_via_ses")
    @patch("apps.mail.services.send_campaign.runner._get_ses_client")
    def test_sent_at_is_set_after_completion(self, mock_client, mock_send):
        mock_client.return_value = MagicMock()
        mock_send.return_value = SesSendResult(message_id="SES-001")
        send_campaign(self.campaign, self.sender)
        self.campaign.refresh_from_db()
        self.assertIsNotNone(self.campaign.sent_at)

    @patch("apps.mail.services.send_campaign.runner._send_via_ses")
    @patch("apps.mail.services.send_campaign.runner._get_ses_client")
    def test_recipient_log_records_provider_message_id(self, mock_client, mock_send):
        mock_client.return_value = MagicMock()
        mock_send.return_value = SesSendResult(message_id="SES-ABC-123")
        send_campaign(self.campaign, self.sender)
        log = RecipientLog.objects.filter(campaign=self.campaign).first()
        self.assertEqual(log.provider_message_id, "SES-ABC-123")
        self.assertEqual(log.status, "sent")
