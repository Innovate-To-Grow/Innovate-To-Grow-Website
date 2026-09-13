"""Keep confirmed SES outcomes consistent with the durable worker job."""

from threading import Event, Thread
from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone

from apps.core.models import BackgroundJob
from apps.core.services.background_jobs import claim_jobs, process_claimed_job, retry_job
from apps.core.services.background_jobs.metrics import worker_metrics
from apps.core.services.background_jobs.worker import UncertainJobError
from apps.core.services.email import DeliveryResult, UncertainEmailDeliveryError
from apps.event.tests.helpers import make_superuser
from apps.mail.models import EmailCampaign, RecipientLog
from apps.mail.services.campaign import dispatch
from apps.mail.services.ses_events import process_sns_envelope
from apps.mail.services.ses_events.handlers import apply_delivery
from apps.mail.tests.services.test_campaign_event_races import event_envelope


class SesJobReconciliationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.sender = make_superuser()
        config = SimpleNamespace(
            provider="ses",
            delivery_configured=True,
            max_send_rate=0,
            source_address="sender@example.com",
            ses_configuration_set_name="campaign-events",
        )
        load_config = patch("apps.mail.services.campaign.dispatch.EmailServiceConfig.load", return_value=config)
        load_config.start()
        self.addCleanup(load_config.stop)

    def queued_campaign(self):
        campaign = EmailCampaign.objects.create(
            subject="Confirmed delivery",
            body="<p>Hello</p>",
            audience_type="manual",
            manual_emails="person@example.com",
        )
        dispatch.queue_email_campaign(campaign, sent_by=self.sender)
        return campaign, campaign.recipient_logs.get()

    @staticmethod
    def timeout_provider(_message, *, before_provider_call, **_kwargs):
        before_provider_call()
        raise UncertainEmailDeliveryError("Response was lost after provider acceptance.")

    def uncertain_delivery(self):
        campaign, log = self.queued_campaign()
        job = claim_jobs(batch_size=1)[0]
        with patch(
            "apps.mail.services.send_campaign.transport.deliver_email",
            side_effect=self.timeout_provider,
        ):
            self.assertFalse(process_claimed_job(job))
        job.refresh_from_db()
        log.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.UNCERTAIN)
        self.assertEqual(log.status, "uncertain")
        self.assertIsNotNone(job.provider_call_started_at)
        self.assertIsNotNone(log.uncertain_at)
        return campaign, log, job

    @staticmethod
    def callback(log, *, event_type="Delivery", attempt=None, message_id=None):
        return event_envelope(
            event_type=event_type,
            message_id=message_id or f"ses-{log.pk}",
            address=log.email_address,
            recipient_id=log.pk,
            attempt=log.attempts if attempt is None else attempt,
        )

    def assert_confirmed(self, campaign, log, job, *, log_status="delivered", success=True):
        campaign.refresh_from_db()
        log.refresh_from_db()
        job.refresh_from_db()
        self.assertEqual(log.status, log_status)
        self.assertEqual(job.status, BackgroundJob.Status.SUCCEEDED if success else BackgroundJob.Status.FAILED)
        self.assertEqual(campaign.status, "sent" if success else "failed")
        self.assertEqual(campaign.sent_count, int(success))
        self.assertEqual(campaign.failed_count, int(not success))
        self.assertIsNone(log.uncertain_at)
        self.assertIsNone(log.claim_token)
        self.assertIsNone(log.claimed_at)
        self.assertIsNone(job.claim_token)
        self.assertIsNone(job.claimed_at)
        self.assertIsNotNone(job.completed_at)
        self.assertEqual(worker_metrics()["uncertain_jobs"], 0)
        if success:
            self.assertEqual(job.last_error, "")
        else:
            self.assertTrue(job.last_error)
            self.assertNotIn("uncertain", job.last_error.lower())

    def test_delivery_after_timeout_completes_job_and_removes_manual_retry(self):
        campaign, log, job = self.uncertain_delivery()
        self.assertEqual(worker_metrics()["uncertain_jobs"], 1)

        process_sns_envelope(self.callback(log))

        self.assert_confirmed(campaign, log, job)
        self.assertFalse(retry_job(job))
        self.assertEqual(claim_jobs(batch_size=1), [])

    def test_delivery_between_result_decision_and_worker_failure_wins(self):
        campaign, log = self.queued_campaign()
        job = claim_jobs(batch_size=1)[0]
        real_record = dispatch._record_email_job_result

        def record_then_callback(recipient, snapshot, result):
            try:
                real_record(recipient, snapshot, result)
            except UncertainJobError:
                process_sns_envelope(self.callback(recipient, attempt=snapshot.attempts))
                raise

        with (
            patch("apps.mail.services.send_campaign.transport.deliver_email", side_effect=self.timeout_provider),
            patch("apps.mail.services.campaign.dispatch._record_email_job_result", side_effect=record_then_callback),
        ):
            process_claimed_job(job)

        self.assert_confirmed(campaign, log, job)
        self.assertFalse(retry_job(job))

    def test_late_definitive_failures_replace_uncertainty(self):
        for event_type, status in (("Bounce", "bounced"), ("Complaint", "complained"), ("Reject", "rejected")):
            with self.subTest(event_type=event_type):
                campaign, log, job = self.uncertain_delivery()
                process_sns_envelope(self.callback(log, event_type=event_type))
                self.assert_confirmed(campaign, log, job, log_status=status, success=False)

    def test_callback_after_dispatch_failure_before_worker_failure_wins(self):
        from apps.core.services.background_jobs import worker

        campaign, log = self.queued_campaign()
        job = claim_jobs(batch_size=1)[0]
        real_fail = worker._fail

        def callback_then_fail(snapshot, error):
            log.refresh_from_db()
            self.assertEqual(log.status, "uncertain")
            self.assertIsNone(log.claim_token)
            process_sns_envelope(self.callback(log))
            real_fail(snapshot, error)

        with (
            patch("apps.mail.services.send_campaign.transport.deliver_email", side_effect=self.timeout_provider),
            patch("apps.core.services.background_jobs.worker._fail", side_effect=callback_then_fail),
        ):
            process_claimed_job(job)

        self.assert_confirmed(campaign, log, job)

    def test_old_attempt_cannot_complete_newly_claimed_manual_retry(self):
        campaign, log, job = self.uncertain_delivery()
        old_attempt = log.attempts
        self.assertTrue(retry_job(job))
        newer = claim_jobs(batch_size=1)[0]
        token = newer.claim_token
        self.assertEqual(newer.attempts, old_attempt + 1)

        process_sns_envelope(self.callback(log, attempt=old_attempt))

        newer.refresh_from_db()
        self.assertEqual(newer.status, BackgroundJob.Status.PROCESSING)
        self.assertEqual(newer.claim_token, token)
        self.assertIsNone(newer.completed_at)

    def test_old_attempt_cannot_touch_new_recipient_claim(self):
        campaign, log, job = self.uncertain_delivery()
        old_attempt = log.attempts
        self.assertTrue(retry_job(job))
        newer = claim_jobs(batch_size=1)[0]
        self.assertTrue(dispatch._mark_email_processing(log, newer))
        token = newer.claim_token

        process_sns_envelope(self.callback(log, attempt=old_attempt))

        log.refresh_from_db()
        newer.refresh_from_db()
        self.assertEqual(newer.status, BackgroundJob.Status.PROCESSING)
        self.assertEqual(newer.claim_token, token)
        self.assertEqual(log.status, "processing")
        self.assertEqual(log.claim_token, token)
        self.assertEqual(log.attempts, newer.attempts)
        self.assertEqual(log.provider_message_id, "")

    def test_later_bounce_does_not_change_successful_submission_job(self):
        campaign, log = self.queued_campaign()
        job = claim_jobs(batch_size=1)[0]
        message_id = f"ses-{log.pk}"

        def accepted(_message, *, before_provider_call, **_kwargs):
            before_provider_call()
            return DeliveryResult(provider="ses", message_id=message_id)

        with patch("apps.mail.services.send_campaign.transport.deliver_email", side_effect=accepted):
            self.assertTrue(process_claimed_job(job))
        job.refresh_from_db()
        completed_at = job.completed_at
        updated_at = job.updated_at
        log.refresh_from_db()

        process_sns_envelope(self.callback(log, event_type="Bounce", message_id=message_id))

        job.refresh_from_db()
        log.refresh_from_db()
        campaign.refresh_from_db()
        self.assertEqual(log.status, "bounced")
        self.assertEqual(campaign.status, "failed")
        self.assertEqual(job.status, BackgroundJob.Status.SUCCEEDED)
        self.assertEqual(job.completed_at, completed_at)
        self.assertEqual(job.updated_at, updated_at)

    def test_callback_does_not_finalize_pending_unclaimed_job(self):
        campaign, log = self.queued_campaign()
        job = BackgroundJob.objects.get(payload__recipient_log_id=str(log.pk))
        log.provider = "ses"
        log.provider_message_id = f"ses-{log.pk}"
        log.save(update_fields=["provider", "provider_message_id"])

        process_sns_envelope(self.callback(log))

        job.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.PENDING)
        self.assertEqual(job.attempts, 0)
        self.assertIsNone(job.completed_at)

    def test_duplicate_callback_reconciles_existing_confirmed_recipient(self):
        campaign, log, job = self.uncertain_delivery()
        envelope = self.callback(log)
        # Recreate the state left by callbacks handled before reconciliation
        # existed: the recipient was confirmed but the job remained uncertain.
        log.provider = "ses"
        log.provider_message_id = f"ses-{log.pk}"
        log.status = "delivered"
        log.sent_at = timezone.now()
        log.delivered_at = timezone.now()
        log.last_sns_message_id = envelope["MessageId"]
        log.uncertain_at = None
        log.error_message = ""
        log.save()
        dispatch.aggregate_email_campaign(campaign.pk)

        process_sns_envelope(envelope)

        self.assert_confirmed(campaign, log, job)

    def test_duplicate_failure_callback_preserves_completion_and_update_times(self):
        campaign, log, job = self.uncertain_delivery()
        envelope = self.callback(log, event_type="Bounce")
        process_sns_envelope(envelope)
        self.assert_confirmed(campaign, log, job, log_status="bounced", success=False)
        completed_at = job.completed_at
        job_updated_at = job.updated_at
        log_updated_at = log.updated_at

        process_sns_envelope(envelope)

        job.refresh_from_db()
        log.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.FAILED)
        self.assertEqual(job.completed_at, completed_at)
        self.assertEqual(job.updated_at, job_updated_at)
        self.assertEqual(log.updated_at, log_updated_at)

    def test_aggregation_failure_rolls_back_confirmation_before_callback_retry(self):
        campaign, log, job = self.uncertain_delivery()
        envelope = self.callback(log)
        before_job = BackgroundJob.objects.values().get(pk=job.pk)
        before_log = RecipientLog.objects.values().get(pk=log.pk)
        before_campaign = EmailCampaign.objects.values().get(pk=campaign.pk)

        with (
            patch(
                "apps.mail.services.campaign.dispatch.aggregate_email_campaign",
                side_effect=RuntimeError("Campaign aggregation failed."),
            ),
            self.assertRaisesRegex(RuntimeError, "Campaign aggregation failed"),
        ):
            process_sns_envelope(envelope)

        self.assertEqual(BackgroundJob.objects.values().get(pk=job.pk), before_job)
        self.assertEqual(RecipientLog.objects.values().get(pk=log.pk), before_log)
        self.assertEqual(EmailCampaign.objects.values().get(pk=campaign.pk), before_campaign)
        self.assertEqual(worker_metrics()["uncertain_jobs"], 1)

        process_sns_envelope(envelope)

        self.assert_confirmed(campaign, log, job)


class SesJobReconciliationConcurrencyTests(TransactionTestCase):
    @skipUnlessDBFeature("has_select_for_update")
    def test_callback_transaction_serializes_with_worker_failure(self):
        from apps.core.services.background_jobs.worker import _fail

        campaign = EmailCampaign.objects.create(
            subject="Concurrent confirmation",
            body="<p>Hello</p>",
            audience_type="manual",
            manual_emails="person@example.com",
        )
        dispatch.queue_email_campaign(campaign, sent_by=make_superuser())
        log = campaign.recipient_logs.get()
        job = claim_jobs(batch_size=1)[0]
        self.assertTrue(dispatch._mark_email_processing(log, job))
        self.assertTrue(job.begin_provider_call())
        callback_has_locks = Event()
        release_callback = Event()
        failure_started = Event()
        failure_done = Event()
        errors = []

        def paused_delivery(recipient, event, sns_message_id):
            apply_delivery(recipient, event, sns_message_id)
            callback_has_locks.set()
            if not release_callback.wait(timeout=10):
                raise TimeoutError("Callback transaction was not released.")

        def receive_callback():
            close_old_connections()
            try:
                process_sns_envelope(SesJobReconciliationTests.callback(log, attempt=job.attempts))
            except Exception as error:
                errors.append(error)
            finally:
                close_old_connections()

        def fail_worker():
            close_old_connections()
            try:
                failure_started.set()
                _fail(job, UncertainJobError("Response was lost after provider acceptance."))
            except Exception as error:
                errors.append(error)
            finally:
                failure_done.set()
                close_old_connections()

        callback_thread = Thread(target=receive_callback)
        worker_thread = Thread(target=fail_worker)
        with patch.dict("apps.mail.services.ses_events.notification.EVENT_HANDLERS", {"Delivery": paused_delivery}):
            callback_thread.start()
            try:
                self.assertTrue(callback_has_locks.wait(timeout=10))
                worker_thread.start()
                self.assertTrue(failure_started.wait(timeout=5))
                self.assertFalse(failure_done.wait(timeout=0.1))
            finally:
                release_callback.set()
                callback_thread.join(timeout=10)
                if worker_thread.ident is not None:
                    worker_thread.join(timeout=10)

        self.assertFalse(callback_thread.is_alive())
        self.assertFalse(worker_thread.is_alive())
        self.assertEqual(errors, [])
        job.refresh_from_db()
        log.refresh_from_db()
        campaign.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.SUCCEEDED)
        self.assertEqual(log.status, "delivered")
        self.assertEqual(campaign.status, "sent")
        self.assertIsNone(job.claim_token)
        self.assertIsNone(log.claim_token)
        self.assertEqual(worker_metrics()["uncertain_jobs"], 0)
