"""The Amplify redirect sync job and its scheduler."""

from datetime import datetime
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.cms.models import CMSPage, RouteRedirect
from apps.cms.services.amplify import (
    AMPLIFY_CONFIGURATION_PAYLOAD_KEY,
    AMPLIFY_REDIRECT_JOB_KIND,
    schedule_amplify_redirect_sync,
)
from apps.core.models import BackgroundJob
from apps.core.services.background_jobs import claim_jobs, process_claimed_job

from ..amplify.amplify_helpers import _client_error


class _AmplifyRedirectJobCase(TestCase):
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


@override_settings(AMPLIFY_APP_ID="app-123", BACKGROUND_JOBS_ENABLED=True)
class AmplifyRedirectJobTests(_AmplifyRedirectJobCase):
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
