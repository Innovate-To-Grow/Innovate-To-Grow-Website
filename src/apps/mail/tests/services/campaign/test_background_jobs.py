import threading
from datetime import timedelta
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from apps.core.models import BackgroundJob
from apps.core.services.background_jobs import (
    claim_jobs,
    recover_stale_jobs,
    retry_job,
)
from apps.event.tests.helpers import make_superuser
from apps.mail.models import EmailCampaign, RecipientLog, SmsCampaign, SmsRecipientLog
from apps.mail.services.campaign.dispatch import (
    aggregate_email_campaign,
    aggregate_sms_campaign,
    dispatch_email_campaign,
    dispatch_sms_campaign,
    queue_email_campaign,
    queue_sms_campaign,
    resolve_stale_delivery_job,
)
from apps.mail.services.campaign.dispatch.launch import _run_in_process_email_campaign, _run_in_process_sms_campaign
from apps.mail.services.campaign.state import campaign_state

from .durable_queue_helpers import DurableCampaignQueueTestCase


class CampaignStateTests(SimpleTestCase):
    def test_campaign_state_covers_empty_active_and_terminal_counts(self):
        cases = [
            ({"total": 0, "sent": 0, "failed": 0}, "sent"),
            ({"total": 3, "sent": 0, "failed": 0, "active": 3}, "queued"),
            ({"total": 3, "sent": 1, "failed": 0, "active": 2}, "sending"),
            ({"total": 3, "sent": 0, "failed": 1, "active": 2}, "sending"),
            ({"total": 3, "sent": 3, "failed": 0}, "sent"),
            ({"total": 3, "sent": 1, "failed": 2}, "partial"),
            ({"total": 3, "sent": 0, "failed": 3}, "failed"),
        ]

        for counts, expected in cases:
            with self.subTest(counts=counts):
                self.assertEqual(campaign_state(**counts), expected)


@override_settings(BACKGROUND_JOBS_ENABLED=False)
class InProcessCampaignDispatchTests(TestCase):
    def setUp(self):
        self.sender = make_superuser()

    @patch("apps.mail.services.campaign.dispatch.launch.start_in_process_task")
    def test_email_dispatch_returns_without_provider_io(self, start_task):
        campaign = EmailCampaign.objects.create(
            name="Legacy email",
            subject="Hello",
            body="Body",
            audience_type="manual",
            manual_emails="person@example.com",
        )

        result = dispatch_email_campaign(campaign, sent_by=self.sender)

        campaign.refresh_from_db()
        self.assertEqual(result, {"total": 0, "sent": 0, "failed": 0})
        self.assertEqual(campaign.status, "sending")
        self.assertEqual(campaign.sent_by, self.sender)
        self.assertFalse(RecipientLog.objects.filter(campaign=campaign).exists())
        start_task.assert_called_once_with(
            _run_in_process_email_campaign,
            campaign.pk,
            self.sender.pk,
            name=f"email-campaign-{campaign.pk}",
            daemon=False,
        )

    @patch("apps.mail.services.campaign.dispatch.launch.start_in_process_task")
    def test_sms_dispatch_returns_without_provider_io(self, start_task):
        campaign = SmsCampaign.objects.create(
            name="Legacy SMS",
            message="Hello",
            audience_type="manual",
            manual_phones="+12095550101",
        )

        result = dispatch_sms_campaign(campaign, sent_by=self.sender)

        campaign.refresh_from_db()
        self.assertEqual(result, {"total": 0, "sent": 0, "failed": 0})
        self.assertEqual(campaign.status, "sending")
        self.assertEqual(campaign.sent_by, self.sender)
        self.assertFalse(SmsRecipientLog.objects.filter(campaign=campaign).exists())
        start_task.assert_called_once_with(
            _run_in_process_sms_campaign,
            campaign.pk,
            self.sender.pk,
            name=f"sms-campaign-{campaign.pk}",
            daemon=False,
        )

    @patch(
        "apps.mail.services.campaign.dispatch.launch.start_in_process_task",
        side_effect=RuntimeError("can't start new thread"),
    )
    def test_email_start_failure_is_persisted_and_propagated(self, _start_task):
        campaign = EmailCampaign.objects.create(
            name="Legacy email startup failure",
            subject="Hello",
            body="Body",
            audience_type="manual",
            manual_emails="person@example.com",
        )

        with self.assertRaisesMessage(RuntimeError, "can't start new thread"):
            dispatch_email_campaign(campaign, sent_by=self.sender)

        campaign.refresh_from_db()
        self.assertEqual(campaign.status, "failed")
        self.assertIn("could not be started", campaign.error_message)

    @patch(
        "apps.mail.services.campaign.dispatch.launch.start_in_process_task",
        side_effect=RuntimeError("can't start new thread"),
    )
    def test_sms_start_failure_is_persisted_and_propagated(self, _start_task):
        campaign = SmsCampaign.objects.create(
            name="Legacy SMS startup failure",
            message="Hello",
            audience_type="manual",
            manual_phones="+12095550101",
        )

        with self.assertRaisesMessage(RuntimeError, "can't start new thread"):
            dispatch_sms_campaign(campaign, sent_by=self.sender)

        campaign.refresh_from_db()
        self.assertEqual(campaign.status, "failed")
        self.assertIn("could not be started", campaign.error_message)


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


@skipUnless(connection.vendor == "postgresql", "PostgreSQL row locking required")
@override_settings(BACKGROUND_JOBS_ENABLED=True)
class DeliveryRecoveryInterleavingTests(TransactionTestCase):
    def test_worker_cannot_claim_manual_retry_before_recipient_mirror_commits(self):
        sender = make_superuser()
        campaign = EmailCampaign.objects.create(
            name="Atomic manual retry",
            subject="Hello",
            body="Body",
            audience_type="manual",
            manual_emails="worker@example.com",
        )
        queue_email_campaign(campaign, sent_by=sender)
        log = RecipientLog.objects.get(campaign=campaign)
        job = claim_jobs()[0]
        completed_at = timezone.now()
        BackgroundJob.objects.filter(pk=job.pk).update(
            status=BackgroundJob.Status.UNCERTAIN,
            claim_token=None,
            claimed_at=None,
            completed_at=completed_at,
        )
        RecipientLog.objects.filter(pk=log.pk).update(
            status="uncertain",
            claim_token=None,
            claimed_at=None,
            uncertain_at=completed_at,
        )
        aggregate_email_campaign(campaign.pk)
        job.refresh_from_db()

        mirror_started = threading.Event()
        release_mirror = threading.Event()
        retry_results = []
        worker_claims = []
        errors = []
        real_aggregate = aggregate_email_campaign

        def blocking_aggregate(campaign_id):
            mirror_started.set()
            if not release_mirror.wait(timeout=5):
                raise TimeoutError("test did not release recipient mirror")
            real_aggregate(campaign_id)

        def retry():
            close_old_connections()
            try:
                retry_results.append(retry_job(job))
            except Exception as exc:  # noqa: BLE001 - surfaced below.
                errors.append(exc)
            finally:
                close_old_connections()

        def claim():
            close_old_connections()
            try:
                worker_claims.append([claimed.pk for claimed in claim_jobs()])
            except Exception as exc:  # noqa: BLE001 - surfaced below.
                errors.append(exc)
            finally:
                close_old_connections()

        with patch(
            "apps.mail.services.campaign.dispatch.job_state.aggregate_email_campaign",
            side_effect=blocking_aggregate,
        ):
            retry_thread = threading.Thread(target=retry)
            retry_thread.start()
            self.assertTrue(mirror_started.wait(timeout=5))

            worker_thread = threading.Thread(target=claim)
            worker_thread.start()
            worker_thread.join(timeout=5)
            self.assertFalse(worker_thread.is_alive())
            release_mirror.set()
            retry_thread.join(timeout=5)

        self.assertFalse(retry_thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(worker_claims, [[]])
        self.assertEqual(retry_results, [True])
        job.refresh_from_db()
        log.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.RETRY)
        self.assertEqual(log.status, "retry")
        self.assertEqual(claim_jobs()[0].pk, job.pk)

    def test_recovery_log_lock_prevents_late_provider_success_from_splitting_state(self):
        sender = make_superuser()
        campaign = EmailCampaign.objects.create(
            name="Interleaved recovery",
            subject="Hello",
            body="Body",
            audience_type="manual",
            manual_emails="worker@example.com",
        )
        queue_email_campaign(campaign, sent_by=sender)
        log = RecipientLog.objects.get(campaign=campaign)
        job = claim_jobs()[0]
        stale_at = timezone.now() - timedelta(hours=1)
        BackgroundJob.objects.filter(pk=job.pk).update(
            claimed_at=stale_at,
            provider_call_started_at=stale_at,
        )
        RecipientLog.objects.filter(pk=log.pk).update(
            status="processing",
            claim_token=job.claim_token,
            claimed_at=stale_at,
        )

        resolver_locked = threading.Event()
        release_recovery = threading.Event()
        provider_attempted = threading.Event()
        provider_updates = []
        recovery_results = []
        errors = []

        def blocking_resolver(current_job):
            result = resolve_stale_delivery_job(current_job)
            resolver_locked.set()
            if not release_recovery.wait(timeout=5):
                raise TimeoutError("test did not release recovery")
            return result

        def recover():
            close_old_connections()
            try:
                recovery_results.append(recover_stale_jobs(stale_after=timedelta(minutes=10)))
            except Exception as exc:  # noqa: BLE001 - surfaced below.
                errors.append(exc)
            finally:
                close_old_connections()

        def record_provider_success():
            close_old_connections()
            try:
                provider_attempted.set()
                provider_updates.append(
                    RecipientLog.objects.filter(
                        pk=log.pk,
                        status="processing",
                        claim_token=job.claim_token,
                    ).update(
                        status="sent",
                        sent_at=timezone.now(),
                        provider_message_id="late-provider-result",
                    )
                )
            except Exception as exc:  # noqa: BLE001 - surfaced below.
                errors.append(exc)
            finally:
                close_old_connections()

        with patch(
            "apps.core.services.background_jobs.recovery.resolve_stale_job_state",
            side_effect=blocking_resolver,
        ):
            recovery_thread = threading.Thread(target=recover)
            recovery_thread.start()
            self.assertTrue(resolver_locked.wait(timeout=5))

            provider_thread = threading.Thread(target=record_provider_success)
            provider_thread.start()
            self.assertTrue(provider_attempted.wait(timeout=5))
            release_recovery.set()

            recovery_thread.join(timeout=5)
            provider_thread.join(timeout=5)

        self.assertFalse(recovery_thread.is_alive())
        self.assertFalse(provider_thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(recovery_results[0]["uncertain"], 1)
        self.assertEqual(provider_updates, [0])
        job.refresh_from_db()
        log.refresh_from_db()
        campaign.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.UNCERTAIN)
        self.assertEqual(log.status, "uncertain")
        self.assertEqual(log.provider_message_id, "")
        self.assertEqual(campaign.status, "failed")
