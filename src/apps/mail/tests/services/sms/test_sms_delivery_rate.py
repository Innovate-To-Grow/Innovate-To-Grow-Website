"""SMS campaigns under the delivery-rate limiter: a queued recipient held back is deferred (never failed), the
in-process sender sends a throttled recipient again after the cooldown, pauses the rest on a long hold, and
"Resume paused recipients" sends exactly those."""

from datetime import timedelta
from unittest.mock import patch

from botocore.exceptions import ClientError
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.models import AWSCredentialConfig, BackgroundJob, DeliveryRateState
from apps.core.services.background_jobs import claim_jobs, process_claimed_job
from apps.core.services.delivery_rates.runtime import context
from apps.event.tests.helpers import make_superuser
from apps.mail.models import SmsCampaign, SmsRecipientLog
from apps.mail.services.campaign.dispatch import queue_sms_campaign, resume_paused_sms_recipients
from apps.mail.services.campaign.dispatch.failures import DEFERRED_LOG_MESSAGE
from apps.mail.services.sms.sender import send_sms_campaign

CLIENT = "apps.core.services.aws.sms_send.boto3.client"
START_TASK = "apps.mail.services.campaign.dispatch.resume.start_in_process_task"
IDENTITY = "us-west-2:+12065550000"
PHONES = ("+12095550101", "+12095550102", "+12095550103")


def run_now(target, *args, **_options):
    target(*args)


def aws_error(code, reason=None):
    response = {"Error": {"Code": code, "Message": "refused"}}
    if reason:
        response["Reason"] = reason
    return ClientError(response, "SendTextMessage")


def hold_back_sms(seconds=3600):
    now = context.clock()
    return DeliveryRateState.objects.create(
        channel="sms_send",
        identity=IDENTITY,
        cooldown_group="sms:us-west-2",
        breaker_state=DeliveryRateState.BreakerState.OPEN,
        breaker_scope=DeliveryRateState.BreakerScope.ALL,
        breaker_reason="spend_limit",
        breaker_retry_at=now + timedelta(seconds=seconds),
        breaker_interval_seconds=seconds,
    )


class SmsCampaignRateTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.sender = make_superuser()
        AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="aws-key",
            secret_access_key="aws-secret",
            default_region="us-west-2",
            sms_from_number="+12065550000",
        )
        patcher = patch(CLIENT)
        self.provider = patcher.start().return_value
        self.addCleanup(patcher.stop)
        self.provider.send_text_message.return_value = {"MessageId": "sms-ok"}

    def campaign(self, phones=PHONES):
        return SmsCampaign.objects.create(
            name="Rates", message="Hello", audience_type="manual", manual_phones="\n".join(phones)
        )

    def sent_to(self):
        return [call.kwargs["DestinationPhoneNumber"] for call in self.provider.send_text_message.call_args_list]


@override_settings(BACKGROUND_JOBS_ENABLED=True)
class QueuedSmsRecipientTests(SmsCampaignRateTestCase):
    def test_a_held_back_recipient_is_deferred_without_a_provider_call_or_a_spent_attempt(self):
        hold_back_sms()
        campaign = self.campaign(phones=PHONES[:1])
        queue_sms_campaign(campaign, sent_by=self.sender)

        self.assertFalse(process_claimed_job(claim_jobs()[0]))

        job = BackgroundJob.objects.get(kind="mail.sms_recipient")
        log = SmsRecipientLog.objects.get(campaign=campaign)
        self.assertEqual((job.status, job.attempts), (BackgroundJob.Status.RETRY, 0))
        self.assertGreater(job.available_at, context.clock() + timedelta(minutes=50))
        self.assertEqual((log.status, log.error_message), ("retry", DEFERRED_LOG_MESSAGE))
        self.provider.send_text_message.assert_not_called()

    def test_aws_throttling_retries_the_recipient_after_the_cooldown(self):
        self.provider.send_text_message.side_effect = aws_error("ThrottlingException")
        campaign = self.campaign(phones=PHONES[:1])
        queue_sms_campaign(campaign, sent_by=self.sender)

        self.assertFalse(process_claimed_job(claim_jobs()[0]))

        job = BackgroundJob.objects.get(kind="mail.sms_recipient")
        self.assertEqual(job.status, BackgroundJob.Status.RETRY)
        self.assertEqual(SmsRecipientLog.objects.get(campaign=campaign).status, "retry")
        state = DeliveryRateState.objects.get(channel="sms_send", identity=IDENTITY)
        self.assertIsNotNone(state.cooldown_until)
        self.assertGreaterEqual(job.available_at, state.cooldown_until - timedelta(seconds=1))


class InProcessSmsCampaignTests(SmsCampaignRateTestCase):
    def test_a_throttled_recipient_is_sent_again_after_the_cooldown(self):
        self.provider.send_text_message.side_effect = [
            aws_error("ThrottlingException"),
            {"MessageId": "first"},
            {"MessageId": "second"},
            {"MessageId": "third"},
        ]
        campaign = self.campaign()

        result = send_sms_campaign(campaign, sent_by=self.sender)

        self.assertEqual(result, {"total": 3, "sent": 3, "failed": 0})
        self.assertEqual(self.sent_to(), [PHONES[0], *PHONES])
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, "sent")

    def test_campaign_texts_go_on_the_bulk_lane(self):
        send_sms_campaign(self.campaign(phones=PHONES[:1]), sent_by=self.sender)

        bucket = DeliveryRateState.objects.get(identity=IDENTITY).usage_buckets.get()
        self.assertEqual((bucket.total, bucket.bulk), (1, 1))

    def test_the_spend_limit_pauses_the_rest_and_the_campaign_ends_partial(self):
        self.provider.send_text_message.side_effect = [
            {"MessageId": "first"},
            aws_error("ServiceQuotaExceededException", "MONTHLY_SPEND_LIMIT_REACHED_FOR_TEXT"),
        ]
        campaign = self.campaign()

        result = send_sms_campaign(campaign, sent_by=self.sender)

        self.assertEqual(result, {"total": 3, "sent": 1, "failed": 0})
        self.assertEqual(self.sent_to(), list(PHONES[:2]))  # the breaker held back every later attempt
        statuses = dict(SmsRecipientLog.objects.values_list("phone_number", "status"))
        self.assertEqual(statuses, {PHONES[0]: "sent", PHONES[1]: "paused", PHONES[2]: "paused"})
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, "partial")
        self.assertIn("Resume paused recipients", campaign.error_message)


class ResumePausedSmsRecipientsTests(SmsCampaignRateTestCase):
    def setUp(self):
        super().setUp()
        self.paused_campaign = self.campaign()
        for phone, status in zip(PHONES, ("sent", "paused", "paused"), strict=True):
            SmsRecipientLog.objects.create(
                campaign=self.paused_campaign, phone_number=phone, status=status, provider="aws_sns"
            )
        SmsCampaign.objects.filter(pk=self.paused_campaign.pk).update(status="partial")

    @override_settings(BACKGROUND_JOBS_ENABLED=False)
    def test_without_the_worker_only_the_paused_recipients_are_sent(self):
        with patch(START_TASK, side_effect=run_now):
            self.assertEqual(resume_paused_sms_recipients(self.paused_campaign), 2)

        self.assertEqual(sorted(self.sent_to()), sorted(PHONES[1:]))
        self.assertEqual(set(SmsRecipientLog.objects.values_list("status", flat=True)), {"sent"})
        self.paused_campaign.refresh_from_db()
        self.assertEqual((self.paused_campaign.status, self.paused_campaign.sent_count), ("sent", 3))

    @override_settings(BACKGROUND_JOBS_ENABLED=True)
    def test_with_the_worker_the_paused_recipients_are_queued_on_the_campaign_lane(self):
        self.assertEqual(resume_paused_sms_recipients(self.paused_campaign), 2)

        jobs = BackgroundJob.objects.filter(kind="mail.sms_recipient")
        paused = SmsRecipientLog.objects.filter(phone_number__in=PHONES[1:])
        self.assertEqual({job.payload["recipient_log_id"] for job in jobs}, {str(log.pk) for log in paused})
        self.assertEqual({job.priority for job in jobs}, {100})
        self.paused_campaign.refresh_from_db()
        self.assertEqual(self.paused_campaign.status, "sending")


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False, BACKGROUND_JOBS_ENABLED=True)
class ResumePausedSmsRecipientsAdminTests(TestCase):
    def setUp(self):
        make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.campaign = SmsCampaign.objects.create(
            name="Paused", message="Hi", audience_type="manual", status="partial"
        )
        SmsRecipientLog.objects.create(campaign=self.campaign, phone_number=PHONES[0], status="paused")
        self.url = reverse("admin:mail_smscampaign_changelist")

    def post(self):
        data = {"action": "resume_paused_recipients_action", ACTION_CHECKBOX_NAME: [str(self.campaign.pk)]}
        return self.client.post(self.url, data, follow=True)

    def test_the_action_resumes_and_says_how(self):
        response = self.post()

        self.assertContains(response, "Resumed 1 paused recipient(s): queued for the background worker.")
        self.assertEqual(BackgroundJob.objects.filter(kind="mail.sms_recipient").count(), 1)

    def test_nothing_to_resume_is_reported(self):
        SmsRecipientLog.objects.update(status="sent")

        self.assertContains(self.post(), "No paused recipients to resume")
