"""Exercise SES callbacks while campaign send responses are still in flight."""

import json
from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from apps.core.models import BackgroundJob
from apps.core.services.background_jobs import claim_jobs, process_claimed_job
from apps.core.services.email import DeliveryResult, UncertainEmailDeliveryError
from apps.event.tests.helpers import make_superuser
from apps.mail.models import EmailCampaign, RecipientLog
from apps.mail.services.campaign.dispatch import queue_email_campaign
from apps.mail.services.send_campaign import send_campaign
from apps.mail.services.ses_events import process_sns_envelope


def event_envelope(*, event_type, message_id, address, recipient_id=None, attempt=1):
    mail = {"messageId": message_id, "destination": [address]}
    if recipient_id is not None:
        mail["tags"] = {
            "i2g_recipient_id": [str(recipient_id)],
            "i2g_delivery_attempt": [str(attempt)],
        }
    return {
        "Type": "Notification",
        "MessageId": f"sns-{message_id}-{event_type}",
        "Message": json.dumps(
            {
                "eventType": event_type,
                "mail": mail,
                "bounce": {"bounceType": "Permanent"},
                "reject": {"reason": "Bad content"},
            }
        ),
    }


class CampaignEventRaceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.sender = make_superuser()
        self.config = SimpleNamespace(
            provider="ses",
            delivery_configured=True,
            max_send_rate=0,
            source_address="sender@example.com",
            ses_configuration_set_name="campaign-events",
        )
        self.load_config = patch(
            "apps.mail.services.send_campaign.runner.EmailServiceConfig.load", return_value=self.config
        )
        self.load_config.start()
        self.addCleanup(self.load_config.stop)

    def campaign(self, count=1):
        return EmailCampaign.objects.create(
            subject="Campaign",
            body="<p>Hello</p>",
            audience_type="manual",
            manual_emails="\n".join(f"person{index}@example.com" for index in range(count)),
        )

    def test_callbacks_during_legacy_send_preserve_totals_and_failure_counts(self):
        for count in (3, 11):
            with self.subTest(recipients=count):
                campaign = self.campaign(count)
                calls = []

                def provider(message, calls=calls, campaign=campaign, count=count, **_kwargs):
                    calls.append(message)
                    self.assertEqual(campaign.recipient_logs.count(), count)
                    if len(calls) == 2:
                        process_sns_envelope(
                            event_envelope(event_type="Bounce", message_id="ses-1", address="person0@example.com")
                        )
                    return DeliveryResult(provider="ses", message_id=f"ses-{len(calls)}")

                with patch("apps.mail.services.send_campaign.transport.deliver_email", side_effect=provider):
                    result = send_campaign(campaign, self.sender)

                campaign.refresh_from_db()
                self.assertEqual(result, {"total": count, "sent": count - 1, "failed": 1})
                self.assertEqual(campaign.total_recipients, count)
                self.assertEqual(campaign.sent_count, count - 1)
                self.assertEqual(campaign.failed_count, 1)
                self.assertEqual(campaign.status, "partial")
                self.assertEqual(campaign.recipient_logs.get(email_address="person0@example.com").status, "bounced")
                # Provider IDs are normally unique; keep this fixture isolated.
                campaign.delete()

    def _early_event(self, *, queued, response_times_out):
        cases = {
            "Bounce": "bounced",
            "Complaint": "complained",
            "Reject": "rejected",
            "Delivery": "delivered",
            "Send": "sent",
            "DeliveryDelay": "sent",
        }
        for event_type, expected_status in cases.items():
            with self.subTest(event=event_type, queued=queued, timeout=response_times_out):
                campaign = self.campaign()
                message_id = f"ses-{campaign.pk}"

                def provider(message, *, before_provider_call, event_type=event_type, message_id=message_id, **_kwargs):
                    if before_provider_call is not None:
                        before_provider_call()
                    tags = dict(item.strip().split("=", 1) for item in message.headers["X-SES-MESSAGE-TAGS"].split(","))
                    process_sns_envelope(
                        event_envelope(
                            event_type=event_type,
                            message_id=message_id,
                            address=message.to[0],
                            recipient_id=tags["i2g_recipient_id"],
                            attempt=tags["i2g_delivery_attempt"],
                        )
                    )
                    if response_times_out:
                        raise UncertainEmailDeliveryError("Response was lost after acceptance.")
                    return DeliveryResult(provider="ses", message_id=message_id)

                with patch("apps.mail.services.send_campaign.transport.deliver_email", side_effect=provider) as send:
                    if queued:
                        queue_email_campaign(campaign, sent_by=self.sender)
                        job = claim_jobs(batch_size=1)[0]
                        process_claimed_job(job)
                    else:
                        send_campaign(campaign, self.sender)
                send.assert_called_once()
                log = campaign.recipient_logs.get()
                campaign.refresh_from_db()
                success = expected_status in {"sent", "delivered"}
                self.assertEqual(log.status, expected_status)
                self.assertEqual(log.provider, "ses")
                self.assertEqual(log.provider_message_id, message_id)
                self.assertTrue(log.last_sns_message_id)
                self.assertIsNotNone(log.sent_at)
                self.assertIsNone(log.uncertain_at)
                self.assertEqual(campaign.status, "sent" if success else "failed")
                self.assertEqual(campaign.sent_count, int(success))
                self.assertEqual(campaign.failed_count, int(not success))
                self.assertEqual(campaign.total_recipients, 1)
                if queued:
                    job.refresh_from_db()
                    self.assertEqual(
                        job.status, BackgroundJob.Status.SUCCEEDED if success else BackgroundJob.Status.FAILED
                    )
                    self.assertIsNone(log.claim_token)
                    self.assertEqual(claim_jobs(batch_size=1), [])

    def test_legacy_send_preserves_events_before_provider_response(self):
        self._early_event(queued=False, response_times_out=False)

    def test_legacy_send_uses_event_confirmation_when_response_times_out(self):
        self._early_event(queued=False, response_times_out=True)

    def test_queued_send_preserves_events_before_provider_response(self):
        self._early_event(queued=True, response_times_out=False)

    def test_queued_send_uses_event_confirmation_when_response_times_out(self):
        self._early_event(queued=True, response_times_out=True)

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

        with patch("apps.mail.services.send_campaign.transport.deliver_email", side_effect=provider):
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
