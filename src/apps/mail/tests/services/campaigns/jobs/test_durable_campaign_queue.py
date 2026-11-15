from datetime import timedelta
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone

from apps.core.models import BackgroundJob
from apps.mail.models import EmailCampaign, RecipientLog, SmsCampaign, SmsRecipientLog
from apps.mail.services.campaign.dispatch import (
    aggregate_email_campaign,
    aggregate_sms_campaign,
    queue_email_campaign,
    queue_sms_campaign,
)

from .durable_queue_helpers import DurableCampaignQueueTestCase


@override_settings(BACKGROUND_JOBS_ENABLED=True)
class DurableCampaignQueueTests(DurableCampaignQueueTestCase):
    """Queueing materializes one log and job per recipient; campaign status is aggregated from the logs."""

    def test_email_campaign_materializes_one_log_and_job_per_recipient(self):
        campaign = EmailCampaign.objects.create(
            name="Durable email",
            subject="Hello",
            body="<p>Body</p>",
            audience_type="manual",
            manual_emails="one@example.com\ntwo@example.com",
        )

        result = queue_email_campaign(campaign, sent_by=self.sender)

        campaign.refresh_from_db()
        self.assertEqual(result, {"total": 2, "sent": 0, "failed": 0})
        self.assertEqual(campaign.status, "queued")
        self.assertEqual(campaign.total_recipients, 2)
        self.assertEqual(RecipientLog.objects.filter(campaign=campaign).count(), 2)
        self.assertEqual(
            BackgroundJob.objects.filter(kind="mail.email_recipient").count(),
            2,
        )
        with self.assertRaisesMessage(ValueError, "no longer in draft"):
            queue_email_campaign(campaign, sent_by=self.sender)
        self.assertEqual(BackgroundJob.objects.filter(kind="mail.email_recipient").count(), 2)

    def test_sms_campaign_materializes_one_log_and_job_per_recipient(self):
        campaign = SmsCampaign.objects.create(
            name="Durable SMS",
            message="Hello",
            audience_type="manual",
            manual_phones="+12095550101\n+12095550102",
        )

        result = queue_sms_campaign(campaign, sent_by=self.sender)

        campaign.refresh_from_db()
        self.assertEqual(result["total"], 2)
        self.assertEqual(campaign.status, "queued")
        self.assertEqual(SmsRecipientLog.objects.filter(campaign=campaign).count(), 2)
        self.assertEqual(
            BackgroundJob.objects.filter(kind="mail.sms_recipient").count(),
            2,
        )

    def test_campaign_status_is_aggregated_from_recipient_logs(self):
        campaign = EmailCampaign.objects.create(
            name="Partial",
            subject="Subject",
            body="Body",
        )
        RecipientLog.objects.create(
            campaign=campaign,
            email_address="sent@example.com",
            status="sent",
        )
        RecipientLog.objects.create(
            campaign=campaign,
            email_address="uncertain@example.com",
            status="uncertain",
        )

        aggregate_email_campaign(campaign.pk)

        campaign.refresh_from_db()
        self.assertEqual(campaign.status, "partial")
        self.assertEqual(campaign.total_recipients, 2)
        self.assertEqual(campaign.sent_count, 1)
        self.assertEqual(campaign.failed_count, 1)

    def test_email_aggregation_locks_campaign_and_preserves_terminal_sent_at(self):
        sent_at = timezone.now() - timedelta(hours=2)
        campaign = EmailCampaign.objects.create(
            name="Stable email timestamp",
            subject="Subject",
            body="Body",
            status="sent",
            sent_at=sent_at,
        )
        log = RecipientLog.objects.create(
            campaign=campaign,
            email_address="sent@example.com",
            status="sent",
        )

        with patch.object(
            EmailCampaign.objects,
            "select_for_update",
            wraps=EmailCampaign.objects.select_for_update,
        ) as lock_campaign:
            aggregate_email_campaign(campaign.pk)

        lock_campaign.assert_called_once_with()
        campaign.refresh_from_db()
        self.assertEqual(campaign.sent_at, sent_at)

        log.status = "bounced"
        log.save(update_fields=["status", "updated_at"])
        aggregate_email_campaign(campaign.pk)
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, "failed")
        self.assertEqual(campaign.sent_at, sent_at)

    def test_sms_aggregation_preserves_terminal_sent_at(self):
        sent_at = timezone.now() - timedelta(hours=2)
        campaign = SmsCampaign.objects.create(
            name="Stable SMS timestamp",
            message="Hello",
            status="sent",
            sent_at=sent_at,
        )
        SmsRecipientLog.objects.create(
            campaign=campaign,
            phone_number="+12095550101",
            status="sent",
        )

        aggregate_sms_campaign(campaign.pk)

        campaign.refresh_from_db()
        self.assertEqual(campaign.status, "sent")
        self.assertEqual(campaign.sent_at, sent_at)
