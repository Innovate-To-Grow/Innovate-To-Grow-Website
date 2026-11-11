"""The SMS policy on the queued (background job) send: quiet hours schedule and defer, the opt-out list ends a
recipient as "Opted out" before any provider call, links turned off fail it with that reason, and the outbox's
mirror keeps each of those outcomes. No provider is called."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import override_settings

from apps.core.models import BackgroundJob
from apps.core.services.aws.sms_errors import SmsOptedOut
from apps.core.services.background_jobs import claim_jobs, process_claimed_job
from apps.event.tests.helpers import make_member
from apps.mail.models import SmsCampaign, SmsLinkToken, SmsRecipientLog
from apps.mail.models.sms_campaign import LINKS_OFF_MESSAGE
from apps.mail.services.campaign.dispatch import (
    queue_sms_campaign,
    resolve_stale_delivery_job,
    resume_paused_sms_recipients,
)
from apps.mail.services.sms.links import open_link
from apps.mail.services.sms.opt_outs import SKIPPED_MESSAGE
from apps.mail.services.sms.quiet_hours import HELD_LOG_MESSAGE

from ..sms.policy_helpers import QUIET_ENDS, QUIET_MOMENT, add_phone, at, opt_out, sms_settings
from .durable_queue_helpers import DurableCampaignQueueTestCase, _provider_failure

SEND = "apps.mail.services.campaign.dispatch.sms_job._send_via_sms"
AWS_CONFIG = "apps.mail.services.campaign.dispatch.sms_job.AWSCredentialConfig.load"
CONFIGURED = Mock(sns_configured=True)


def clock(moment):
    return SimpleNamespace(now=lambda: moment)


@override_settings(BACKGROUND_JOBS_ENABLED=True)
@patch(AWS_CONFIG, return_value=CONFIGURED)
class QueuedSmsPolicyTests(DurableCampaignQueueTestCase):
    def test_a_campaign_queued_in_quiet_hours_is_due_when_they_end(self, _config):
        campaign = SmsCampaign.objects.create(
            name="Night", message="Hi", audience_type="manual", manual_phones="+12095550101"
        )
        with at(QUIET_MOMENT), patch("apps.mail.services.campaign.dispatch.launch.timezone", clock(QUIET_MOMENT)):
            queue_sms_campaign(campaign, sent_by=self.sender)

        log = SmsRecipientLog.objects.get(campaign=campaign)
        job = BackgroundJob.objects.get(kind="mail.sms_recipient")
        self.assertEqual((log.available_at, job.available_at), (QUIET_ENDS, QUIET_ENDS))

    @patch(SEND)
    def test_a_job_that_reaches_quiet_hours_is_deferred_to_their_end_with_its_attempt_refunded(self, send, _config):
        _campaign, log = self._queued_sms()
        job = claim_jobs()[0]

        with at(QUIET_MOMENT):
            self.assertFalse(process_claimed_job(job))

        send.assert_not_called()
        job.refresh_from_db()
        log.refresh_from_db()
        self.assertEqual((job.status, job.attempts), (BackgroundJob.Status.RETRY, 0))
        self.assertGreaterEqual(job.available_at, QUIET_ENDS)
        # The outbox mirrored the retry but kept the handler's reason.
        self.assertEqual((log.status, log.error_message), ("retry", HELD_LOG_MESSAGE))

    @patch(SEND)
    def test_a_number_that_opted_out_after_queueing_is_not_sent(self, send, _config):
        campaign, log = self._queued_sms()
        opt_out("+12095550101")

        self.assertTrue(process_claimed_job(claim_jobs()[0]))

        send.assert_not_called()
        log.refresh_from_db()
        campaign.refresh_from_db()
        self.assertEqual((log.status, log.error_message), ("opted_out", SKIPPED_MESSAGE))
        self.assertEqual((campaign.status, campaign.sent_count, campaign.failed_count), ("sent", 0, 0))
        self.assertEqual(BackgroundJob.objects.get().status, BackgroundJob.Status.SUCCEEDED)
        self.assertEqual(resolve_stale_delivery_job(BackgroundJob.objects.get()), BackgroundJob.Status.SUCCEEDED)

    @patch(SEND)
    def test_a_job_for_a_recipient_already_opted_out_only_recounts(self, send, _config):
        campaign, log = self._queued_sms()
        SmsRecipientLog.objects.filter(pk=log.pk).update(status="opted_out")

        self.assertTrue(process_claimed_job(claim_jobs()[0]))

        send.assert_not_called()
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, "sent")

    @patch(SEND, side_effect=_provider_failure(SmsOptedOut(code="ConflictException", refused_by_provider=True)))
    def test_aws_refusing_the_number_as_opted_out_ends_it_as_opted_out(self, _send, _config):
        campaign, log = self._queued_sms()

        self.assertTrue(process_claimed_job(claim_jobs()[0]))

        log.refresh_from_db()
        self.assertEqual(log.status, "opted_out")
        campaign.refresh_from_db()
        self.assertEqual(campaign.failed_count, 0)

    @patch(SEND)
    def test_links_turned_off_after_queueing_fail_it_with_that_reason(self, send, _config):
        campaign = SmsCampaign.objects.create(
            name="Links", message="Sign in: {{login_link}}", audience_type="manual", manual_phones="+12095550101"
        )
        queue_sms_campaign(campaign, sent_by=self.sender)

        self.assertTrue(process_claimed_job(claim_jobs()[0]))

        send.assert_not_called()
        log = SmsRecipientLog.objects.get(campaign=campaign)
        self.assertEqual((log.status, log.error_message), ("failed", LINKS_OFF_MESSAGE))
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, "failed")

    @override_settings(FRONTEND_URL="https://i2g.example.edu")
    @patch(SEND, return_value="msg-1")
    def test_a_sent_text_carries_its_links_and_the_footer(self, send, _config):
        sms_settings(links_enabled=True)
        campaign = SmsCampaign.objects.create(
            name="Links", message="Sign in: {{login_link}}", audience_type="manual", manual_phones="+12095550101"
        )
        queue_sms_campaign(campaign, sent_by=self.sender)

        self.assertTrue(process_claimed_job(claim_jobs()[0]))

        message = send.call_args.kwargs["message"]
        self.assertTrue(message.startswith("Sign in: https://i2g.example.edu/l/"))
        self.assertTrue(message.endswith("\nReply STOP to opt out."))
        self.assertEqual(SmsRecipientLog.objects.get(campaign=campaign).status, "sent")

    @override_settings(FRONTEND_URL="https://i2g.example.edu")
    @patch(SEND, return_value="msg-1")
    def test_a_log_pointed_at_another_member_never_texts_their_sign_in_link(self, send, _config):
        """Security review H1: a log whose member was changed (the /admin-api/ CLI can write recipient logs) must not
        text that member's one-tap sign-in link to the log's phone."""
        sms_settings(links_enabled=True, personal_links_enabled=True)
        victim = make_member(email="victim@example.com")
        add_phone(victim, "2095550123")
        campaign = SmsCampaign.objects.create(
            name="Repoint", message="Hi {{login_link}}", audience_type="manual", manual_phones="+12095550199"
        )
        queue_sms_campaign(campaign, sent_by=self.sender)
        SmsRecipientLog.objects.filter(campaign=campaign).update(member=victim)

        self.assertTrue(process_claimed_job(claim_jobs()[0]))

        self.assertEqual(send.call_args.kwargs["phone_number"], "+12095550199")
        self.assertFalse(SmsLinkToken.objects.filter(member__isnull=False).exists())
        token = send.call_args.kwargs["message"].split("/l/")[1].split()[0]
        self.assertEqual(open_link(token).kind, "redirect")

    def test_resumed_recipients_in_quiet_hours_are_due_when_they_end(self, _config):
        campaign, log = self._queued_sms()
        SmsRecipientLog.objects.filter(pk=log.pk).update(status="paused")
        SmsCampaign.objects.filter(pk=campaign.pk).update(status="partial")
        BackgroundJob.objects.all().delete()

        with at(QUIET_MOMENT), patch("apps.mail.services.campaign.dispatch.resume.timezone", clock(QUIET_MOMENT)):
            self.assertEqual(resume_paused_sms_recipients(campaign), 1)

        log.refresh_from_db()
        self.assertEqual((log.status, log.available_at), ("pending", QUIET_ENDS))
        self.assertEqual(BackgroundJob.objects.get().available_at, QUIET_ENDS)
