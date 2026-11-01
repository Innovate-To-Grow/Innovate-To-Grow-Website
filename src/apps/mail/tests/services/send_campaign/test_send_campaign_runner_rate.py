"""The in-process campaign sender (used while background jobs are off) under the delivery-rate limiter: every
message goes on the bulk lane and may wait for its slot; a long hold pauses the rest of the campaign."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.models import AWSCredentialConfig, EmailServiceConfig
from apps.core.services.delivery_rates import Lane, RateDeferred, WaitMode
from apps.core.services.delivery_rates.runtime import context
from apps.core.services.email import DeliveryResult
from apps.core.services.email.exceptions import EmailRateDeferred
from apps.core.tests.services.delivery_rates.helpers import rates_with
from apps.event.tests.helpers import make_member
from apps.mail.models import EmailCampaign, RecipientLog
from apps.mail.services.send_campaign.runner import PAUSED_LOG_MESSAGE, send_campaign

DELIVER = "apps.mail.services.send_campaign.transport.deliver_email"


def held_back(seconds=3600):
    now = timezone.now()
    return EmailRateDeferred(RateDeferred(now + timedelta(seconds=seconds), "budget:daily_limit", now=now))


class RunnerDeliveryRateTests(TestCase):
    def setUp(self):
        AWSCredentialConfig.objects.create(
            name="AWS", is_active=True, access_key_id="AKID", secret_access_key="SECRET", default_region="us-west-2"
        )
        for name in ("alice", "bob", "carol"):
            make_member(email=f"{name}@example.com", first_name=name.title(), last_name="Smith")
        self.sender = make_member(email="admin@example.com", first_name="Admin", last_name="User")
        self.campaign = EmailCampaign.objects.create(
            subject="Hi", body="<p>Hello</p>", audience_type="subscribers", member_email_scope="primary", status="draft"
        )
        EmailServiceConfig.objects.create(is_active=True, provider="ses", from_email="noreply@example.com")
        patcher = patch("apps.mail.services.send_campaign.runner._get_ses_client", side_effect=lambda config: config)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_every_message_goes_on_the_bulk_lane_and_may_wait_in_the_dedicated_mode(self):
        modes = []

        def deliver(message, **kwargs):
            modes.append((kwargs["lane"], context.current_wait_mode()))
            return DeliveryResult(provider="ses", message_id=f"id-{len(modes)}")

        with patch(DELIVER, side_effect=deliver):
            result = send_campaign(self.campaign, self.sender)

        self.assertEqual(modes, [(Lane.BULK, WaitMode.DEDICATED)] * 4)
        self.assertEqual((result["sent"], result["failed"]), (4, 0))

    def test_a_long_hold_pauses_the_remaining_recipients_and_ends_the_campaign_partial(self):
        outcomes = [DeliveryResult(provider="ses", message_id="id-1"), held_back()]
        with patch(DELIVER, side_effect=outcomes) as deliver:
            send_campaign(self.campaign, self.sender)

        self.assertEqual(deliver.call_count, 2)  # nobody after the held-back recipient was tried
        statuses = sorted(RecipientLog.objects.filter(campaign=self.campaign).values_list("status", flat=True))
        self.assertEqual(statuses, ["paused", "paused", "paused", "sent"])
        self.assertEqual(
            set(RecipientLog.objects.filter(status="paused").values_list("error_message", flat=True)),
            {PAUSED_LOG_MESSAGE},
        )
        self.campaign.refresh_from_db()
        self.assertEqual(
            (self.campaign.status, self.campaign.sent_count, self.campaign.failed_count), ("partial", 1, 0)
        )
        self.assertIn("Resume paused recipients", self.campaign.error_message)

    @override_settings(DELIVERY_RATES=rates_with(jobs={"runner_refresh_recipients": 2}))
    def test_the_configuration_is_read_again_every_few_recipients(self):
        loads = MagicMock(wraps=EmailServiceConfig.load)
        with (
            patch(DELIVER, return_value=DeliveryResult(provider="ses", message_id="id")),
            patch("apps.mail.services.send_campaign.runner.EmailServiceConfig.load", loads),
        ):
            send_campaign(self.campaign, self.sender)

        # Once to start, then after the second and the fourth recipient.
        self.assertEqual(loads.call_count, 3)
