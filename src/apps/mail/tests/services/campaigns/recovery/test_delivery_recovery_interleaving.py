import threading
from datetime import timedelta
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from apps.core.models import BackgroundJob
from apps.core.services.background_jobs import (
    claim_jobs,
    recover_stale_jobs,
    retry_job,
)
from apps.event.tests.helpers import make_superuser
from apps.mail.models import EmailCampaign, RecipientLog
from apps.mail.services.campaign.dispatch import (
    aggregate_email_campaign,
    queue_email_campaign,
    resolve_stale_delivery_job,
)


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
