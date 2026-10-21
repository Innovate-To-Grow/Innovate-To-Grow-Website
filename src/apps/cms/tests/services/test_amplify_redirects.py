"""The Amplify redirect sync job and its scheduler."""

from datetime import datetime, timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.cms.models import CMSPage, RouteRedirect
from apps.cms.services.amplify import (
    AMPLIFY_CONFIGURATION_PAYLOAD_KEY,
    AMPLIFY_REDIRECT_JOB_KIND,
    get_amplify_redirect_sync_status,
    schedule_amplify_redirect_sync,
)
from apps.core.models import BackgroundJob
from apps.core.services.background_jobs import claim_jobs, process_claimed_job

from .amplify_helpers import _client_error


@override_settings(AMPLIFY_APP_ID="app-123", BACKGROUND_JOBS_ENABLED=True)
class AmplifyRedirectJobTests(TestCase):
    def setUp(self):
        CMSPage.objects.create(
            slug="job-target",
            route="/job-target",
            title="Job target",
            status="published",
        )
        self.redirect = RouteRedirect.objects.create(
            source_path="/job-legacy",
            destination_path="/job-target",
            is_active=True,
        )

    def test_scheduler_coalesces_pending_jobs_and_immediate_retry_removes_delay(self):
        first = schedule_amplify_redirect_sync()
        first_requested_at = first.payload["requested_at"]
        self.assertGreater(first.available_at, timezone.now())

        second = schedule_amplify_redirect_sync(immediate=True)

        self.assertEqual(second.pk, first.pk)
        self.assertEqual(BackgroundJob.objects.filter(kind=AMPLIFY_REDIRECT_JOB_KIND).count(), 1)
        self.assertLessEqual(second.available_at, timezone.now())
        self.assertNotEqual(second.payload["requested_at"], first_requested_at)

    def test_scheduler_revision_time_remains_strictly_monotonic_when_clock_is_equal(self):
        frozen_time = timezone.now()
        with patch.object(timezone, "now", return_value=frozen_time):
            first = schedule_amplify_redirect_sync(immediate=True)
            first_requested_at = first.payload["requested_at"]
            second = schedule_amplify_redirect_sync(immediate=True)

        self.assertGreater(
            datetime.fromisoformat(second.payload["requested_at"]),
            datetime.fromisoformat(first_requested_at),
        )

    @patch("apps.cms.services.amplify.reconcile.reconcile_amplify_redirects")
    def test_successful_job_marks_redirect_synced(self, reconcile):
        job = schedule_amplify_redirect_sync(immediate=True)
        queued_configuration = job.payload[AMPLIFY_CONFIGURATION_PAYLOAD_KEY]

        self.assertTrue(process_claimed_job(claim_jobs(batch_size=1)[0]))

        self.redirect.refresh_from_db()
        self.assertEqual(self.redirect.edge_sync_status, RouteRedirect.EdgeSyncStatus.SYNCED)
        self.assertEqual(self.redirect.edge_sync_error, "")
        self.assertIsNotNone(self.redirect.edge_sync_attempted_at)
        self.assertIsNotNone(self.redirect.edge_synced_at)
        reconcile.assert_called_once_with(configuration=queued_configuration)

    @override_settings(
        AMPLIFY_CONFIG_REVISION="200.1",
        AWS_REGION="us-east-1",
        AMPLIFY_BACKEND_PROXY_URL="https://new-api.example/",
        AMPLIFY_PROXY_ADMIN_PATHS=True,
    )
    def test_job_uses_queued_configuration_during_a_rolling_deploy(self):
        job = schedule_amplify_redirect_sync(immediate=True)
        queued_configuration = job.payload[AMPLIFY_CONFIGURATION_PAYLOAD_KEY]
        self.assertEqual(
            queued_configuration,
            {
                "config_revision": "200.1",
                "app_id": "app-123",
                "region": "us-east-1",
                "backend_proxy_url": "https://new-api.example",
                "proxy_admin_paths": True,
            },
        )

        with (
            override_settings(
                AWS_REGION="us-west-2",
                AMPLIFY_BACKEND_PROXY_URL="https://old-api.example",
                AMPLIFY_PROXY_ADMIN_PATHS=False,
            ),
            patch("apps.cms.services.amplify.reconcile.reconcile_amplify_redirects") as reconcile,
        ):
            self.assertTrue(process_claimed_job(claim_jobs(batch_size=1)[0]))

        reconcile.assert_called_once_with(configuration=queued_configuration)

    def test_older_web_task_carries_forward_newer_persisted_configuration(self):
        with override_settings(
            AMPLIFY_CONFIG_REVISION="300.1",
            AWS_REGION="us-east-1",
            AMPLIFY_BACKEND_PROXY_URL="https://new-api.example",
            AMPLIFY_PROXY_ADMIN_PATHS=True,
        ):
            newer = schedule_amplify_redirect_sync(immediate=True)
            newer_configuration = newer.payload[AMPLIFY_CONFIGURATION_PAYLOAD_KEY]

        with patch("apps.cms.services.amplify.reconcile.reconcile_amplify_redirects"):
            self.assertTrue(process_claimed_job(claim_jobs(batch_size=1)[0]))

        with override_settings(
            AMPLIFY_CONFIG_REVISION="299.9",
            AWS_REGION="us-west-2",
            AMPLIFY_BACKEND_PROXY_URL="https://old-api.example",
            AMPLIFY_PROXY_ADMIN_PATHS=False,
        ):
            queued_by_old_web = schedule_amplify_redirect_sync(immediate=True)

        self.assertNotEqual(queued_by_old_web.pk, newer.pk)
        self.assertEqual(
            queued_by_old_web.payload[AMPLIFY_CONFIGURATION_PAYLOAD_KEY],
            newer_configuration,
        )

    @patch(
        "apps.cms.services.amplify.reconcile.reconcile_amplify_redirects",
        side_effect=_client_error("ThrottlingException", 429),
    )
    def test_transient_amplify_failure_is_retried_and_visible(self, _reconcile):
        job = schedule_amplify_redirect_sync(immediate=True)

        self.assertFalse(process_claimed_job(claim_jobs(batch_size=1)[0]))

        job.refresh_from_db()
        self.redirect.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.RETRY)
        self.assertEqual(self.redirect.edge_sync_status, RouteRedirect.EdgeSyncStatus.PENDING)
        self.assertIn("temporarily unavailable", self.redirect.edge_sync_error)
        self.assertNotIn("provider detail", self.redirect.edge_sync_error)

    @patch(
        "apps.cms.services.amplify.reconcile.reconcile_amplify_redirects",
        side_effect=_client_error("AccessDeniedException", 403),
    )
    def test_permanent_amplify_failure_is_marked_failed(self, _reconcile):
        job = schedule_amplify_redirect_sync(immediate=True)

        self.assertFalse(process_claimed_job(claim_jobs(batch_size=1)[0]))

        job.refresh_from_db()
        self.redirect.refresh_from_db()
        self.assertEqual(job.status, BackgroundJob.Status.FAILED)
        self.assertEqual(self.redirect.edge_sync_status, RouteRedirect.EdgeSyncStatus.FAILED)
        self.assertIn("rejected", self.redirect.edge_sync_error)
        self.assertNotIn("provider detail", self.redirect.edge_sync_error)

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

    @patch("apps.cms.services.amplify.jobs.schedule_amplify_redirect_sync")
    def test_deactivation_schedules_followup_even_before_ownership_is_confirmed(self, schedule):
        redirect = RouteRedirect.objects.create(
            source_path="/in-flight-deactivation",
            destination_path="/job-target",
            is_active=True,
        )
        self.assertFalse(redirect.edge_rule_managed)
        redirect.is_active = False

        with self.captureOnCommitCallbacks(execute=True):
            redirect.save(update_fields=["is_active", "updated_at"])

        redirect.refresh_from_db()
        self.assertEqual(redirect.edge_sync_status, RouteRedirect.EdgeSyncStatus.PENDING)
        schedule.assert_called_once_with(redirect_ids=(redirect.pk,))


@override_settings(AMPLIFY_APP_ID="", BACKGROUND_JOBS_ENABLED=True)
class AmplifyUnconfiguredSchedulerTests(TestCase):
    def test_missing_app_id_leaves_redirect_pending_without_a_job(self):
        self.assertIsNone(schedule_amplify_redirect_sync(immediate=True))
        self.assertFalse(BackgroundJob.objects.filter(kind=AMPLIFY_REDIRECT_JOB_KIND).exists())
