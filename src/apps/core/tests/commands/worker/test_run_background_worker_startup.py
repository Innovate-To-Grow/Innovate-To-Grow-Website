import signal
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings

from apps.core.management.commands import run_background_worker
from apps.core.management.operations import worker_maintenance
from apps.core.models import BackgroundJob
from apps.core.services.background_jobs import enqueue_job


class RunBackgroundWorkerStartupTests(SimpleTestCase):
    @override_settings(BACKGROUND_JOBS_ENABLED=False, AMPLIFY_APP_ID="app-123")
    def test_startup_reconciliation_respects_background_jobs_rollout_flag(self):
        with patch(
            "apps.cms.services.amplify.jobs.schedule_amplify_redirect_sync",
        ) as schedule:
            self.assertFalse(run_background_worker.schedule_startup_reconciliation())

        schedule.assert_not_called()

    @override_settings(BACKGROUND_JOBS_ENABLED=True, AMPLIFY_APP_ID="")
    def test_startup_reconciliation_requires_amplify_app(self):
        with patch(
            "apps.cms.services.amplify.jobs.schedule_amplify_redirect_sync",
        ) as schedule:
            self.assertFalse(run_background_worker.schedule_startup_reconciliation())

        schedule.assert_not_called()

    @override_settings(BACKGROUND_JOBS_ENABLED=True, AMPLIFY_APP_ID="app-123")
    def test_startup_reconciliation_is_immediate(self):
        with patch(
            "apps.cms.services.amplify.jobs.schedule_amplify_redirect_sync",
            return_value=SimpleNamespace(pk=1),
        ) as schedule:
            with self.assertLogs(run_background_worker.logger, level="INFO"):
                self.assertTrue(run_background_worker.schedule_startup_reconciliation())

        schedule.assert_called_once_with(immediate=True)

    @override_settings(BACKGROUND_JOBS_ENABLED=True, AMPLIFY_APP_ID="app-123")
    def test_startup_reconciliation_failure_does_not_stop_worker(self):
        with patch(
            "apps.cms.services.amplify.jobs.schedule_amplify_redirect_sync",
            side_effect=RuntimeError("provider unavailable"),
        ):
            with self.assertLogs(run_background_worker.logger, level="ERROR"):
                self.assertFalse(run_background_worker.schedule_startup_reconciliation())


class RunBackgroundWorkerShutdownTests(TestCase):
    def test_sigterm_does_not_claim_unstarted_jobs_or_consume_attempts(self):
        first, _created = enqueue_job(kind="test.echo", dedupe_key="shutdown-first", payload={})
        second, _created = enqueue_job(kind="test.echo", dedupe_key="shutdown-second", payload={})
        installed_handlers = {}

        def install_handler(signum, handler):
            installed_handlers[signum] = handler

        def stop_after_current_job(_job):
            installed_handlers[signal.SIGTERM](signal.SIGTERM, None)

        command = run_background_worker.Command(stdout=StringIO())
        with (
            patch.object(run_background_worker.signal, "signal", side_effect=install_handler),
            patch.object(worker_maintenance, "purge_retired_auth_keypairs", return_value=0),
            patch.object(worker_maintenance, "purge_expired_public_assistant_budgets", return_value=0),
            patch.object(run_background_worker, "schedule_startup_reconciliation"),
            patch.object(run_background_worker, "recover_stale_jobs"),
            patch.object(run_background_worker, "worker_metrics", return_value={"heartbeat": 1}),
            patch.object(run_background_worker, "publish_worker_metrics"),
            patch(
                "apps.core.services.background_jobs.worker.get_handler",
                return_value=stop_after_current_job,
            ),
        ):
            command.handle(
                once=True,
                batch_size=2,
                poll_seconds=0.25,
                stale_minutes=10,
                key_purge_seconds=3600,
            )

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.status, BackgroundJob.Status.SUCCEEDED)
        self.assertEqual(first.attempts, 1)
        self.assertEqual(second.status, BackgroundJob.Status.PENDING)
        self.assertEqual(second.attempts, 0)
