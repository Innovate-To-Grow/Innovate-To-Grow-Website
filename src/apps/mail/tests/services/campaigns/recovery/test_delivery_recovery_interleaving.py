import threading
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from apps.core.models import BackgroundJob
from apps.core.services.background_jobs import (
    claim_jobs,
    retry_job,
)
from apps.event.tests.helpers import make_superuser
from apps.mail.models import EmailCampaign, RecipientLog
from apps.mail.services.campaign.dispatch import (
    aggregate_email_campaign,
    queue_email_campaign,
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
