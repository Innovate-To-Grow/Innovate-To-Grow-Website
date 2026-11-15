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
)
from apps.event.tests.helpers import make_superuser
from apps.mail.models import EmailCampaign, RecipientLog
from apps.mail.services.campaign.dispatch import (
    queue_email_campaign,
    resolve_stale_delivery_job,
)


@skipUnless(connection.vendor == "postgresql", "PostgreSQL row locking required")
@override_settings(BACKGROUND_JOBS_ENABLED=True)
class DeliveryRecoveryInterleavingTests(TransactionTestCase):
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
