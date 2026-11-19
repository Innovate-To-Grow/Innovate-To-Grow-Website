from unittest.mock import patch

from apps.core.models import BackgroundJob
from apps.core.services.background_jobs import claim_jobs, process_claimed_job, retry_job
from apps.core.services.background_jobs.worker import UncertainJobError
from apps.mail.services.campaign import dispatch
from apps.mail.services.email_monitoring.ses_events import process_sns_envelope
from apps.mail.tests.services.ses_events.notifications.test_ses_job_reconciliation import _SesJobReconciliationCase


class SesJobReconciliationTests(_SesJobReconciliationCase):
    def test_delivery_between_result_decision_and_worker_failure_wins(self):
        campaign, log = self.queued_campaign()
        job = claim_jobs(batch_size=1)[0]
        real_record = dispatch.email_job._record_email_job_result

        def record_then_callback(recipient, snapshot, result):
            try:
                real_record(recipient, snapshot, result)
            except UncertainJobError:
                process_sns_envelope(self.callback(recipient, attempt=snapshot.attempts))
                raise

        with (
            patch("apps.mail.services.campaign.send.transport.deliver_email", side_effect=self.timeout_provider),
            patch(
                "apps.mail.services.campaign.dispatch.email_job._record_email_job_result",
                side_effect=record_then_callback,
            ),
        ):
            process_claimed_job(job)

        self.assert_confirmed(campaign, log, job)
        self.assertFalse(retry_job(job))

    def test_late_definitive_failures_replace_uncertainty(self):
        for event_type, status in (("Bounce", "bounced"), ("Complaint", "complained"), ("Reject", "rejected")):
            with self.subTest(event_type=event_type):
                campaign, log, job = self.uncertain_delivery(address=f"{event_type.lower()}@example.com")
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
            patch("apps.mail.services.campaign.send.transport.deliver_email", side_effect=self.timeout_provider),
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
        self.assertTrue(dispatch.channels.mark_log_processing(dispatch.channels.EMAIL, log, newer))
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
