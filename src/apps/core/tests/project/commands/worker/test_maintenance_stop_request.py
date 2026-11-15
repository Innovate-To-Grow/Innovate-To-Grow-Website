import signal
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.sessions.models import Session
from django.db.models.query import QuerySet
from django.test import TestCase
from django.utils import timezone

from apps.authn.models import LoginFailureWindow, SendVerificationChallenge
from apps.core.management.commands import run_background_worker
from apps.core.tests.project.commands.worker.test_run_background_worker import LOGGER_NAME


class MaintenanceStopRequestTests(TestCase):
    """A stop request during maintenance ends the run after the batch in flight (real services, real rows)."""

    BATCH = 1000  # the services' default batch size

    def make_old_challenges(self, count):
        expired = timezone.now() - timedelta(days=30)
        SendVerificationChallenge.objects.bulk_create(
            SendVerificationChallenge(
                operation="login.request_code",
                destination_kind="email",
                destination_normalized=f"user{index}@example.com",
                principal_type="session",
                algorithm="PBKDF2/SHA-256",
                cost=10,
                expires_at=expired,
                status=SendVerificationChallenge.Status.CONSUMED,
            )
            for index in range(count)
        )

    def make_backlog(self):
        now = timezone.now()
        self.make_old_challenges(2 * self.BATCH + 5)
        Session.objects.create(session_key="expired".ljust(32, "x"), session_data="e30", expire_date=now - timedelta(1))
        LoginFailureWindow.objects.create(
            identifier_digest="a" * 64, window="15m", window_index=1, failure_count=1, expires_at=now - timedelta(1)
        )

    def stop_during_the_first_challenge_batch(self, request_stop):
        """Patch the batch delete so ``request_stop`` is called while the first batch is being deleted."""
        original = QuerySet._raw_delete
        batches = []

        def raw_delete(queryset, using):
            deleted = original(queryset, using)
            if queryset.model is SendVerificationChallenge:
                batches.append(deleted)
                if len(batches) == 1:
                    request_stop()
            return deleted

        patcher = patch.object(QuerySet, "_raw_delete", raw_delete)
        patcher.start()
        self.addCleanup(patcher.stop)
        return batches

    def assert_only_the_first_batch_was_cleaned(self, batches):
        self.assertEqual(batches, [self.BATCH])
        self.assertEqual(SendVerificationChallenge.objects.count(), self.BATCH + 5)
        # The steps after it never started.
        self.assertEqual(Session.objects.count(), 1)
        self.assertEqual(LoginFailureWindow.objects.count(), 1)

    def test_run_maintenance_stops_after_the_batch_in_flight(self):
        self.make_backlog()
        stopping = []
        batches = self.stop_during_the_first_challenge_batch(lambda: stopping.append(True))

        with self.assertLogs(LOGGER_NAME, level="INFO") as logs:
            run_background_worker.run_maintenance(should_stop=lambda: bool(stopping))

        self.assert_only_the_first_batch_was_cleaned(batches)
        self.assertEqual(
            logs.output,
            [
                f"INFO:{LOGGER_NAME}:Send verification cleanup: expired 0 challenges; deleted {self.BATCH} "
                "challenges and 0 send requests"
            ],
        )

    def test_sigterm_during_maintenance_ends_the_worker_without_finishing_the_backlog(self):
        self.make_backlog()
        handlers = {}
        batches = self.stop_during_the_first_challenge_batch(lambda: handlers[signal.SIGTERM](signal.SIGTERM, None))

        with (
            patch.object(run_background_worker.signal, "signal", side_effect=handlers.__setitem__),
            patch.object(run_background_worker, "schedule_startup_reconciliation"),
            patch.object(run_background_worker, "recover_stale_jobs") as recover,
            patch.object(run_background_worker, "claim_jobs", return_value=[]) as claim,
            patch.object(run_background_worker, "worker_metrics", return_value={"heartbeat": 1}),
            patch.object(run_background_worker, "publish_worker_metrics"),
            patch.object(run_background_worker.time, "sleep") as sleep,
        ):
            run_background_worker.Command(stdout=StringIO()).handle(
                once=False, batch_size=5, poll_seconds=5, stale_minutes=10, key_purge_seconds=3600
            )

        self.assert_only_the_first_batch_was_cleaned(batches)
        recover.assert_called_once()
        claim.assert_not_called()  # stopping: no job is claimed after the interrupted maintenance run
        sleep.assert_not_called()  # and the worker does not sit out an idle poll before exiting

    def test_the_next_run_finishes_the_backlog(self):
        self.make_backlog()
        stopping = []
        self.stop_during_the_first_challenge_batch(lambda: stopping.append(True))
        with self.assertLogs(LOGGER_NAME, level="INFO"):
            run_background_worker.run_maintenance(should_stop=lambda: bool(stopping))

        with self.assertLogs(LOGGER_NAME, level="INFO"):
            run_background_worker.run_maintenance(should_stop=lambda: False)

        self.assertFalse(SendVerificationChallenge.objects.exists())
        self.assertFalse(Session.objects.exists())
        self.assertFalse(LoginFailureWindow.objects.exists())
