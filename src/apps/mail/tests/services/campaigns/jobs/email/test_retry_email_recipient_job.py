"""Durable retry jobs recheck live eligibility at provider-call time and use their method snapshot."""

from unittest.mock import Mock, patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.authn.models import ContactEmail
from apps.core.models import BackgroundJob
from apps.core.services.background_jobs import claim_jobs, process_claimed_job
from apps.event.tests.helpers import make_superuser
from apps.mail.models import RecipientLog
from apps.mail.services.campaign.dispatch import queue_email_campaign
from apps.mail.services.campaign.send import SesSendResult
from apps.mail.tests.services.campaigns.retry.helpers import make_retry_campaign


@override_settings(BACKGROUND_JOBS_ENABLED=True)
class RetryEmailRecipientJobTests(TestCase):
    def setUp(self):
        self.sender = make_superuser()

    @patch("apps.mail.services.campaign.dispatch.email_job._get_ses_client", return_value=Mock())
    @patch("apps.mail.services.campaign.dispatch.email_job._send_via_ses")
    def test_eligibility_change_inside_before_provider_callback_blocks_send(self, send, _get_client):
        retry, _source, member, _row, _config = make_retry_campaign()
        queue_email_campaign(retry, sent_by=self.sender)
        provider_touched = False

        def change_then_enter_provider(*, before_provider_call, **_kwargs):
            nonlocal provider_touched
            ContactEmail.objects.filter(member=member, email_address=retry.retry_address).update(subscribe=False)
            before_provider_call()
            provider_touched = True
            return SesSendResult(message_id="must-not-send")

        send.side_effect = change_then_enter_provider
        result = process_claimed_job(claim_jobs()[0])

        log = RecipientLog.objects.get(campaign=retry)
        job = BackgroundJob.objects.get(kind="mail.email_recipient")
        self.assertFalse(result)
        self.assertFalse(provider_touched)
        self.assertEqual((job.status, log.status), (BackgroundJob.Status.FAILED, "failed"))
        self.assertFalse(log.provider_message_id)

    @patch("apps.mail.services.campaign.dispatch.email_job._get_ses_client", return_value=Mock())
    @patch("apps.mail.services.campaign.dispatch.email_job._send_via_ses")
    def test_fresh_unaggregated_complaint_at_provider_boundary_blocks_send(self, send, _get_client):
        retry, source, _member, row, _config = make_retry_campaign()
        queue_email_campaign(retry, sent_by=self.sender)
        source_log = RecipientLog.objects.get(campaign=source)
        self.assertEqual(row.complaint_count, 0)
        provider_touched = False

        def complain_then_enter_provider(*, before_provider_call, **_kwargs):
            nonlocal provider_touched
            RecipientLog.objects.filter(pk=source_log.pk).update(complained_at=timezone.now())
            before_provider_call()
            provider_touched = True
            return SesSendResult(message_id="must-not-send")

        send.side_effect = complain_then_enter_provider
        result = process_claimed_job(claim_jobs()[0])

        log = RecipientLog.objects.get(campaign=retry)
        self.assertFalse(result)
        self.assertFalse(provider_touched)
        self.assertEqual(log.status, "failed")
        self.assertFalse(log.provider_message_id)

    @patch("apps.mail.services.campaign.dispatch.email_job._get_ses_client", side_effect=lambda config: config)
    @patch("apps.mail.services.campaign.dispatch.email_job._send_via_ses")
    def test_worker_uses_retry_snapshot_after_global_method_switch(self, send, _get_client):
        retry, _source, _member, _row, config = make_retry_campaign()
        queue_email_campaign(retry, sent_by=self.sender)
        config.provider = "smtp"
        config.from_email = "global-now@example.org"
        config.from_name = "Global now"
        config.save(update_fields=["provider", "from_email", "from_name", "updated_at"])

        def accept(*, before_provider_call, **_kwargs):
            before_provider_call()
            return SesSendResult(message_id="snapshot-send", provider="ses")

        send.side_effect = accept
        self.assertTrue(process_claimed_job(claim_jobs()[0]))

        kwargs = send.call_args.kwargs
        self.assertEqual(kwargs["ses_client"].provider, "ses")
        self.assertEqual(kwargs["source"], "I2G <snapshot@example.org>")
        self.assertEqual(kwargs["configuration_set"], "retry-config-set")
