from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings

from apps.event.tests.helpers import make_superuser
from apps.mail.models import EmailCampaign, RecipientLog, SmsCampaign, SmsRecipientLog
from apps.mail.services.campaign.delivery.state import campaign_state
from apps.mail.services.campaign.dispatch import (
    dispatch_email_campaign,
    dispatch_sms_campaign,
)
from apps.mail.services.campaign.dispatch.launch import _run_in_process_email_campaign, _run_in_process_sms_campaign


class CampaignStateTests(SimpleTestCase):
    def test_campaign_state_covers_empty_active_and_terminal_counts(self):
        cases = [
            ({"total": 0, "sent": 0, "failed": 0}, "sent"),
            ({"total": 3, "sent": 0, "failed": 0, "active": 3}, "queued"),
            ({"total": 3, "sent": 1, "failed": 0, "active": 2}, "sending"),
            ({"total": 3, "sent": 0, "failed": 1, "active": 2}, "sending"),
            ({"total": 3, "sent": 3, "failed": 0}, "sent"),
            ({"total": 3, "sent": 1, "failed": 2}, "partial"),
            ({"total": 3, "sent": 0, "failed": 3}, "failed"),
        ]

        for counts, expected in cases:
            with self.subTest(counts=counts):
                self.assertEqual(campaign_state(**counts), expected)


@override_settings(BACKGROUND_JOBS_ENABLED=False)
class InProcessCampaignDispatchTests(TestCase):
    def setUp(self):
        self.sender = make_superuser()

    @patch("apps.mail.services.campaign.dispatch.launch.start_in_process_task")
    def test_email_dispatch_returns_without_provider_io(self, start_task):
        campaign = EmailCampaign.objects.create(
            name="Legacy email",
            subject="Hello",
            body="Body",
            audience_type="manual",
            manual_emails="person@example.com",
        )

        result = dispatch_email_campaign(campaign, sent_by=self.sender)

        campaign.refresh_from_db()
        self.assertEqual(result, {"total": 0, "sent": 0, "failed": 0})
        self.assertEqual(campaign.status, "sending")
        self.assertEqual(campaign.sent_by, self.sender)
        self.assertFalse(RecipientLog.objects.filter(campaign=campaign).exists())
        start_task.assert_called_once_with(
            _run_in_process_email_campaign,
            campaign.pk,
            self.sender.pk,
            name=f"email-campaign-{campaign.pk}",
            daemon=False,
        )

    @patch("apps.mail.services.campaign.dispatch.launch.start_in_process_task")
    def test_sms_dispatch_returns_without_provider_io(self, start_task):
        campaign = SmsCampaign.objects.create(
            name="Legacy SMS",
            message="Hello",
            audience_type="manual",
            manual_phones="+12095550101",
        )

        result = dispatch_sms_campaign(campaign, sent_by=self.sender)

        campaign.refresh_from_db()
        self.assertEqual(result, {"total": 0, "sent": 0, "failed": 0})
        self.assertEqual(campaign.status, "sending")
        self.assertEqual(campaign.sent_by, self.sender)
        self.assertFalse(SmsRecipientLog.objects.filter(campaign=campaign).exists())
        start_task.assert_called_once_with(
            _run_in_process_sms_campaign,
            campaign.pk,
            self.sender.pk,
            name=f"sms-campaign-{campaign.pk}",
            daemon=False,
        )

    @patch(
        "apps.mail.services.campaign.dispatch.launch.start_in_process_task",
        side_effect=RuntimeError("can't start new thread"),
    )
    def test_email_start_failure_is_persisted_and_propagated(self, _start_task):
        campaign = EmailCampaign.objects.create(
            name="Legacy email startup failure",
            subject="Hello",
            body="Body",
            audience_type="manual",
            manual_emails="person@example.com",
        )

        with self.assertRaisesMessage(RuntimeError, "can't start new thread"):
            dispatch_email_campaign(campaign, sent_by=self.sender)

        campaign.refresh_from_db()
        self.assertEqual(campaign.status, "failed")
        self.assertIn("could not be started", campaign.error_message)

    @patch(
        "apps.mail.services.campaign.dispatch.launch.start_in_process_task",
        side_effect=RuntimeError("can't start new thread"),
    )
    def test_sms_start_failure_is_persisted_and_propagated(self, _start_task):
        campaign = SmsCampaign.objects.create(
            name="Legacy SMS startup failure",
            message="Hello",
            audience_type="manual",
            manual_phones="+12095550101",
        )

        with self.assertRaisesMessage(RuntimeError, "can't start new thread"):
            dispatch_sms_campaign(campaign, sent_by=self.sender)

        campaign.refresh_from_db()
        self.assertEqual(campaign.status, "failed")
        self.assertIn("could not be started", campaign.error_message)
