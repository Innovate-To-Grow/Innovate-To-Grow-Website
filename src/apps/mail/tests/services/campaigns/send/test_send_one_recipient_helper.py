from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.core.models import EmailServiceConfig
from apps.event.tests.helpers import make_member
from apps.mail.models import EmailCampaign, RecipientLog
from apps.mail.services.campaign.errors import UNEXPECTED_DELIVERY_ERROR
from apps.mail.services.send_campaign.runner import send_campaign
from apps.mail.services.send_campaign.transport import SesSendResult
from apps.mail.tests.services.campaigns.send.test_send_campaign_runner import _make_active_aws


class SendOneRecipientHelperTests(TestCase):
    """Direct-call coverage for runner helpers and edge branches."""

    def setUp(self):
        self.config = EmailServiceConfig.objects.create(
            is_active=True,
            from_email="noreply@example.com",
            from_name="Test",
            max_send_rate=0,
        )
        self.campaign = EmailCampaign.objects.create(
            subject="Hi",
            body="<p>Body</p>",
            audience_type="subscribers",
            member_email_scope="primary",
            status="draft",
            total_recipients=1,
        )

    def test_send_with_configured_provider_returns_unconfigured_when_no_client(self):
        from apps.mail.services.send_campaign.runner import _send_with_configured_provider

        result = _send_with_configured_provider(
            config=self.config,
            ses_client=None,
            configuration_set="",
            recipient="x@example.com",
            subject="s",
            wrapped_html="<p>h</p>",
            unsubscribe_url="",
        )

        self.assertEqual(result.provider, "")
        self.assertEqual(result.error, "Email delivery is not configured.")

    def test_configured_provider_returns_empty_when_no_client(self):
        from apps.mail.services.send_campaign.runner import _configured_provider

        self.assertEqual(_configured_provider(None), "")
        self.assertEqual(_configured_provider(self.config), "ses")

    @patch(
        "apps.mail.services.send_campaign.runner.personalize",
        side_effect=RuntimeError("smtp://user:private-value@internal-host/private/path"),
    )
    def test_send_one_recipient_records_failure_on_exception(self, mock_personalize):
        from apps.mail.services.send_campaign.runner import _send_one_recipient

        recipient = {
            "member_id": None,
            "email": "boom@example.com",
            "full_name": "Boom User",
            "first_name": "Boom",
            "last_name": "User",
        }

        with self.assertLogs("apps.mail.services.send_campaign.runner", level="ERROR") as captured:
            _send_one_recipient(self.campaign, self.config, MagicMock(), "", recipient)

        log = RecipientLog.objects.get(campaign=self.campaign, email_address="boom@example.com")
        self.assertEqual(log.status, "failed")
        # Exception internals stay in the server log; the stored message that the
        # admin renders only carries the exception class.
        self.assertEqual(log.error_message, f"{UNEXPECTED_DELIVERY_ERROR} (RuntimeError)")
        self.assertNotIn("private-value", log.error_message)
        self.assertNotIn("internal-host", log.error_message)
        self.assertIn("private-value@internal-host", "\n".join(captured.output))
        self.assertEqual(self.campaign.failed_count, 1)

    def test_record_send_result_handles_external_status_change(self):
        from apps.mail.services.send_campaign.runner import _record_send_result

        log = RecipientLog.objects.create(
            campaign=self.campaign,
            email_address="race@example.com",
            status="pending",
        )
        # Simulate an SES webhook flipping the log to 'bounced' before we record.
        RecipientLog.objects.filter(pk=log.pk).update(status="bounced")

        _record_send_result(self.campaign, log, SesSendResult(message_id="X", provider="ses"))

        # The race branch counts a terminal bounce as a failure.
        self.assertEqual(self.campaign.failed_count, 1)
        self.assertEqual(self.campaign.sent_count, 0)

    def test_record_send_result_external_non_terminal_counts_sent(self):
        from apps.mail.services.send_campaign.runner import _record_send_result

        log = RecipientLog.objects.create(
            campaign=self.campaign,
            email_address="delivered@example.com",
            status="pending",
        )
        RecipientLog.objects.filter(pk=log.pk).update(status="delivered")

        _record_send_result(self.campaign, log, SesSendResult(message_id="X", provider="ses"))

        self.assertEqual(self.campaign.sent_count, 1)
        self.assertEqual(self.campaign.failed_count, 0)


class SendCampaignPeriodicSaveTests(TestCase):
    @patch("apps.mail.services.send_campaign.runner._send_via_ses")
    @patch("apps.mail.services.send_campaign.runner._get_ses_client")
    def test_periodic_save_runs_for_many_recipients(self, mock_client, mock_send):
        _make_active_aws()
        EmailServiceConfig.objects.create(
            is_active=True,
            from_email="noreply@example.com",
            from_name="Test",
            max_send_rate=0,
        )
        sender = make_member(email="sender@example.com", first_name="S", last_name="S")
        # 11 manual recipients ensures the (sent+failed) % 10 == 0 branch fires.
        emails = "\n".join(f"user{i}@example.com" for i in range(11))
        campaign = EmailCampaign.objects.create(
            subject="Bulk",
            body="<p>Hi</p>",
            audience_type="manual",
            manual_emails=emails,
            status="draft",
        )
        mock_client.return_value = MagicMock()
        mock_send.return_value = SesSendResult(message_id="OK")

        send_campaign(campaign, sender)

        campaign.refresh_from_db()
        self.assertEqual(campaign.total_recipients, 11)
        self.assertEqual(campaign.sent_count, 11)
        self.assertEqual(campaign.status, "sent")
