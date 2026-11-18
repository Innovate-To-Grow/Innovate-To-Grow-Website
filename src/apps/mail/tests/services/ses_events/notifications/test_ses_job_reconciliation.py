"""Keep confirmed SES outcomes consistent with the durable worker job."""

from threading import Event, Thread
from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature

from apps.core.models import BackgroundJob
from apps.core.services.background_jobs import claim_jobs, process_claimed_job, retry_job
from apps.core.services.background_jobs.metrics import worker_metrics
from apps.core.services.background_jobs.worker import UncertainJobError
from apps.core.services.email import UncertainEmailDeliveryError
from apps.event.tests.helpers import make_superuser
from apps.mail.models import EmailCampaign
from apps.mail.services.campaign import dispatch
from apps.mail.services.email_monitoring.ses_events import process_sns_envelope
from apps.mail.services.email_monitoring.ses_events.handlers import apply_delivery
from apps.mail.tests.services.campaigns.recovery.test_campaign_event_races import event_envelope


class _SesJobReconciliationCase(TestCase):
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
        load_config = patch(
            "apps.mail.services.campaign.dispatch.email_job.EmailServiceConfig.load", return_value=config
        )
        load_config.start()
        self.addCleanup(load_config.stop)

    def queued_campaign(self, address="person@example.com"):
        campaign = EmailCampaign.objects.create(
            subject="Confirmed delivery",
            body="<p>Hello</p>",
            audience_type="manual",
            manual_emails=address,
        )
        dispatch.queue_email_campaign(campaign, sent_by=self.sender)
        return campaign, campaign.recipient_logs.get()

    @staticmethod
    def timeout_provider(_message, *, before_provider_call, **_kwargs):
        before_provider_call()
        raise UncertainEmailDeliveryError("Response was lost after provider acceptance.")

    def uncertain_delivery(self, address="person@example.com"):
        campaign, log = self.queued_campaign(address)
        job = claim_jobs(batch_size=1)[0]
        with patch(
            "apps.mail.services.campaign.send.transport.deliver_email",
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


class SesJobReconciliationTests(_SesJobReconciliationCase):
    def test_delivery_after_timeout_completes_job_and_removes_manual_retry(self):
        campaign, log, job = self.uncertain_delivery()
        self.assertEqual(worker_metrics()["uncertain_jobs"], 1)

        process_sns_envelope(self.callback(log))

        self.assert_confirmed(campaign, log, job)
        self.assertFalse(retry_job(job))
        self.assertEqual(claim_jobs(batch_size=1), [])


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
        self.assertTrue(dispatch.channels.mark_log_processing(dispatch.channels.EMAIL, log, job))
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
        with patch.dict(
            "apps.mail.services.email_monitoring.ses_events.notification.EVENT_HANDLERS", {"Delivery": paused_delivery}
        ):
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
