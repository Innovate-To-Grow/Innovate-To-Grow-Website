from unittest.mock import patch

from apps.core.services.background_jobs import claim_jobs, process_claimed_job
from apps.core.services.email import UncertainEmailDeliveryError
from apps.mail.models import RecipientLog
from apps.mail.services.campaign.dispatch import queue_email_campaign
from apps.mail.services.email_monitoring.ses_events import process_sns_envelope
from apps.mail.tests.services.campaigns.recovery.test_campaign_event_races import (
    _CampaignEventRaceCase,
    event_envelope,
)


class CampaignEventRaceTests(_CampaignEventRaceCase):
    def test_tagged_events_cannot_bind_another_attempt_recipient_or_provider(self):
        campaign = self.campaign()
        log = RecipientLog.objects.create(campaign=campaign, email_address="person0@example.com", attempts=2)
        cases = [
            {"attempt": 1},
            {"address": "another@example.com"},
            {"recipient_id": "invalid-uuid"},
            {"attempt": "invalid-attempt"},
            {"attempt": 0},
        ]
        for overrides in cases:
            with self.subTest(overrides=overrides):
                values = {
                    "event_type": "Bounce",
                    "message_id": "ses-unrelated",
                    "address": log.email_address,
                    "recipient_id": log.pk,
                    "attempt": 2,
                    **overrides,
                }
                process_sns_envelope(event_envelope(**values))
                log.refresh_from_db()
                self.assertEqual(log.status, "pending")
                self.assertEqual(log.provider_message_id, "")

        log.provider = "smtp"
        log.save(update_fields=["provider"])
        process_sns_envelope(
            event_envelope(
                event_type="Bounce",
                message_id="ses-unrelated",
                address=log.email_address,
                recipient_id=log.pk,
                attempt=2,
            )
        )
        log.refresh_from_db()
        self.assertEqual(log.status, "pending")
        self.assertEqual(log.provider, "smtp")

    def test_callback_after_uncertain_result_can_confirm_the_same_attempt(self):
        campaign = self.campaign()
        queue_email_campaign(campaign, sent_by=self.sender)
        job = claim_jobs(batch_size=1)[0]

        def provider(_message, *, before_provider_call, **_kwargs):
            before_provider_call()
            raise UncertainEmailDeliveryError("Response was lost.")

        with patch("apps.mail.services.campaign.send.transport.deliver_email", side_effect=provider):
            process_claimed_job(job)
        log = campaign.recipient_logs.get()
        self.assertEqual(log.status, "uncertain")
        process_sns_envelope(
            event_envelope(
                event_type="Delivery",
                message_id="ses-delayed",
                address=log.email_address,
                recipient_id=log.pk,
                attempt=1,
            )
        )
        log.refresh_from_db()
        campaign.refresh_from_db()
        self.assertEqual(log.status, "delivered")
        self.assertEqual(campaign.status, "sent")
        self.assertIsNone(log.uncertain_at)
