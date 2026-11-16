from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone

from apps.cms.models import CMSPage, RouteRedirect
from apps.cms.services.amplify import (
    AMPLIFY_CONFIGURATION_PAYLOAD_KEY,
    AMPLIFY_REDIRECT_JOB_KIND,
    get_amplify_redirect_sync_status,
    schedule_amplify_redirect_sync,
)
from apps.cms.tests.services.amplify_redirects.test_amplify_redirects import _AmplifyRedirectJobCase
from apps.core.models import BackgroundJob
from apps.core.services.background_jobs import claim_jobs, process_claimed_job


@override_settings(AMPLIFY_APP_ID="app-123", BACKGROUND_JOBS_ENABLED=True)
class AmplifyRedirectJobTests(_AmplifyRedirectJobCase):
    def test_newer_edit_stays_pending_when_an_older_job_completes(self):
        schedule_amplify_redirect_sync(immediate=True)
        claimed = claim_jobs(batch_size=1)[0]
        newer_time = timezone.now() + timedelta(milliseconds=1)
        RouteRedirect.objects.filter(pk=self.redirect.pk).update(
            destination_path="/job-target",
            updated_at=newer_time,
            edge_sync_status=RouteRedirect.EdgeSyncStatus.PENDING,
        )

        with patch("apps.cms.services.amplify.reconcile.reconcile_amplify_redirects"):
            self.assertTrue(process_claimed_job(claimed))

        self.redirect.refresh_from_db()
        self.assertEqual(self.redirect.edge_sync_status, RouteRedirect.EdgeSyncStatus.PENDING)

    def test_older_claim_never_cancels_a_newer_requested_revision(self):
        older = schedule_amplify_redirect_sync(immediate=True)
        claimed = claim_jobs(batch_size=1)[0]
        self.assertEqual(claimed.pk, older.pk)
        newer_requested_at = timezone.now() + timedelta(milliseconds=1)
        newer = BackgroundJob.objects.create(
            kind=AMPLIFY_REDIRECT_JOB_KIND,
            dedupe_key="concurrent-newer-revision",
            payload={
                "requested_at": newer_requested_at.isoformat(),
                "requested_redirect_ids": [str(self.redirect.pk)],
            },
            available_at=timezone.now(),
        )

        with patch("apps.cms.services.amplify.reconcile.reconcile_amplify_redirects") as reconcile:
            self.assertTrue(process_claimed_job(claimed))

        older.refresh_from_db()
        newer.refresh_from_db()
        self.assertEqual(older.status, BackgroundJob.Status.CANCELLED)
        reconcile.assert_not_called()
        self.assertEqual(newer.status, BackgroundJob.Status.PENDING)
        self.assertIsNone(newer.completed_at)
        self.assertEqual(newer.last_error, "")

    def test_two_processing_jobs_cannot_write_provider_revisions_in_reverse(self):
        older = schedule_amplify_redirect_sync(immediate=True)
        (older_claim,) = claim_jobs(batch_size=1)
        self.assertEqual(older_claim.pk, older.pk)

        newer = schedule_amplify_redirect_sync(immediate=True)
        (newer_claim,) = claim_jobs(batch_size=1)
        self.assertEqual(newer_claim.pk, newer.pk)

        with patch("apps.cms.services.amplify.reconcile.reconcile_amplify_redirects") as reconcile:
            self.assertTrue(process_claimed_job(newer_claim))
            self.assertTrue(process_claimed_job(older_claim))

        older.refresh_from_db()
        newer.refresh_from_db()
        self.assertEqual(newer.status, BackgroundJob.Status.SUCCEEDED)
        self.assertEqual(older.status, BackgroundJob.Status.CANCELLED)
        reconcile.assert_called_once_with(configuration=newer.payload[AMPLIFY_CONFIGURATION_PAYLOAD_KEY])

    def test_claim_does_not_cancel_an_equal_timestamp_revision(self):
        older = schedule_amplify_redirect_sync(immediate=True)
        claimed = claim_jobs(batch_size=1)[0]
        same_timestamp = BackgroundJob.objects.create(
            kind=AMPLIFY_REDIRECT_JOB_KIND,
            dedupe_key="concurrent-equal-timestamp-revision",
            payload={
                "requested_at": older.payload["requested_at"],
                "requested_redirect_ids": [str(self.redirect.pk)],
            },
            available_at=timezone.now(),
        )

        with patch("apps.cms.services.amplify.reconcile.reconcile_amplify_redirects"):
            self.assertTrue(process_claimed_job(claimed))

        same_timestamp.refresh_from_db()
        self.assertEqual(same_timestamp.status, BackgroundJob.Status.PENDING)
        self.assertIsNone(same_timestamp.completed_at)

    def test_status_helper_exposes_latest_durable_job(self):
        job = schedule_amplify_redirect_sync(immediate=True)

        status = get_amplify_redirect_sync_status()

        self.assertTrue(status["configured"])
        self.assertTrue(status["jobs_enabled"])
        self.assertEqual(status["job_id"], str(job.pk))
        self.assertEqual(status["status"], BackgroundJob.Status.PENDING)

    def test_inactive_create_invalidates_cache_without_enqueuing(self):
        cache_key = "cms:page:/signal-legacy"
        cache.set(cache_key, {"stale": True})

        with self.captureOnCommitCallbacks(execute=True):
            redirect = RouteRedirect.objects.create(
                source_path="/signal-legacy",
                destination_path="/job-target",
                is_active=False,
            )

        redirect.refresh_from_db()
        self.assertIsNone(cache.get(cache_key))
        self.assertEqual(redirect.edge_sync_status, RouteRedirect.EdgeSyncStatus.PENDING)
        self.assertFalse(BackgroundJob.objects.filter(kind=AMPLIFY_REDIRECT_JOB_KIND).exists())

    @patch("apps.cms.services.amplify.jobs.schedule_amplify_redirect_sync")
    def test_inactive_notes_and_destination_edits_do_not_schedule(self, schedule):
        other_target = CMSPage.objects.create(
            slug="other-job-target",
            route="/other-job-target",
            title="Other job target",
            status="published",
        )
        redirect = RouteRedirect.objects.create(
            source_path="/inactive-edit",
            destination_path="/job-target",
            is_active=False,
        )
        redirect.notes = "Documentation only"
        redirect.destination_path = other_target.route

        with self.captureOnCommitCallbacks(execute=True):
            redirect.save(update_fields=["notes", "destination_path", "updated_at"])

        schedule.assert_not_called()

    @patch("apps.cms.services.amplify.jobs.schedule_amplify_redirect_sync")
    def test_managed_inactive_edit_reschedules_pending_cleanup(self, schedule):
        redirect = RouteRedirect.objects.create(
            source_path="/managed-inactive-edit",
            destination_path="/job-target",
            is_active=False,
        )
        RouteRedirect.objects.filter(pk=redirect.pk).update(
            edge_rule_managed=True,
            edge_sync_status=RouteRedirect.EdgeSyncStatus.FAILED,
        )
        redirect.refresh_from_db()
        redirect.notes = "Retry cleanup after this edit"

        with self.captureOnCommitCallbacks(execute=True):
            redirect.save(update_fields=["notes", "updated_at"])

        redirect.refresh_from_db()
        self.assertEqual(redirect.edge_sync_status, RouteRedirect.EdgeSyncStatus.PENDING)
        schedule.assert_called_once_with(redirect_ids=(redirect.pk,))
