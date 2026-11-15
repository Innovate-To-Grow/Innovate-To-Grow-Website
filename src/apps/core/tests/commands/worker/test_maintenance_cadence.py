import signal
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.sessions.models import Session
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.authn.models import LoginFailureWindow, SendVerificationChallenge
from apps.core.management.commands import run_background_worker
from apps.core.tests.commands.worker.test_run_background_worker import LOGGER_NAME


class MaintenanceCadenceTests(SimpleTestCase):
    def run_cycles(self, *, cycles, cycle_seconds, key_purge_seconds):
        """Run the real loop for ``cycles`` idle cycles of ``cycle_seconds`` each; return when maintenance ran."""
        clock = {"now": 1000.0}
        runs, handlers, slept = [], {}, []

        def fake_sleep(_seconds):
            clock["now"] += cycle_seconds
            slept.append(clock["now"])
            if len(slept) >= cycles:
                handlers[signal.SIGTERM](signal.SIGTERM, None)

        with (
            patch.object(run_background_worker.signal, "signal", side_effect=handlers.__setitem__),
            patch.object(run_background_worker.time, "monotonic", side_effect=lambda: clock["now"]),
            patch.object(run_background_worker.time, "sleep", side_effect=fake_sleep),
            patch.object(run_background_worker, "run_maintenance", side_effect=lambda **_: runs.append(clock["now"])),
            patch.object(run_background_worker, "schedule_startup_reconciliation"),
            patch.object(run_background_worker, "recover_stale_jobs"),
            patch.object(run_background_worker, "claim_jobs", return_value=[]),
            patch.object(run_background_worker, "worker_metrics", return_value={"heartbeat": 1}),
            patch.object(run_background_worker, "publish_worker_metrics"),
        ):
            run_background_worker.Command(stdout=StringIO()).handle(
                once=False,
                batch_size=1,
                poll_seconds=5,
                stale_minutes=10,
                key_purge_seconds=key_purge_seconds,
            )
        return runs

    def test_maintenance_runs_at_start_then_once_per_interval(self):
        # Cycles at t = 1000, 2000, ..., 9000: due at 1000, then 1000 + 3600 and 5000 + 3600.
        self.assertEqual(self.run_cycles(cycles=9, cycle_seconds=1000, key_purge_seconds=3600), [1000, 5000, 9000])

    def test_the_interval_has_a_five_minute_floor(self):
        runs = self.run_cycles(cycles=6, cycle_seconds=100, key_purge_seconds=1)

        self.assertEqual(runs, [1000, 1300])

    def test_both_option_names_set_the_interval(self):
        parser = run_background_worker.Command().create_parser("manage.py", "run_background_worker")

        self.assertEqual(parser.parse_args([]).key_purge_seconds, 3600)
        self.assertEqual(parser.parse_args(["--key-purge-seconds", "600"]).key_purge_seconds, 600)
        self.assertEqual(parser.parse_args(["--maintenance-seconds", "900"]).key_purge_seconds, 900)


class MaintenanceDatabaseTests(TestCase):
    """The real tasks against the database: expired sessions, send-verification and login-window rows go, live
    ones stay."""

    def test_maintenance_purges_only_ended_login_failure_windows(self):
        now = timezone.now()
        ended = LoginFailureWindow.objects.create(
            identifier_digest="a" * 64, window="15m", window_index=1, failure_count=10, expires_at=now - timedelta(1)
        )
        LoginFailureWindow.objects.create(
            identifier_digest=LoginFailureWindow.GLOBAL_DIGEST,
            window="5m",
            window_index=1,
            failure_count=3,
            expires_at=now - timedelta(1),
        )
        live = LoginFailureWindow.objects.create(
            identifier_digest="a" * 64, window="24h", window_index=1, failure_count=30, expires_at=now + timedelta(1)
        )

        with self.assertLogs(LOGGER_NAME, level="INFO") as logs:
            run_background_worker.run_maintenance()

        self.assertEqual(list(LoginFailureWindow.objects.values_list("pk", flat=True)), [live.pk])
        self.assertFalse(LoginFailureWindow.objects.filter(pk=ended.pk).exists())
        self.assertEqual(logs.output, [f"INFO:{LOGGER_NAME}:Purged 2 expired login failure windows"])

    def test_maintenance_clears_expired_sessions_and_send_verification_rows(self):
        now = timezone.now()
        Session.objects.bulk_create(
            [
                Session(session_key="expired-one".ljust(32, "x"), session_data="e30", expire_date=now - timedelta(1)),
                Session(session_key="expired-two".ljust(32, "x"), session_data="e30", expire_date=now - timedelta(1)),
                Session(session_key="live".ljust(32, "x"), session_data="e30", expire_date=now + timedelta(1)),
            ]
        )
        SendVerificationChallenge.objects.create(
            operation="login.request_code",
            destination_kind="email",
            destination_normalized="user@example.com",
            principal_type="session",
            algorithm="PBKDF2/SHA-256",
            cost=10,
            expires_at=now - timedelta(days=30),
            status=SendVerificationChallenge.Status.CONSUMED,
        )

        with self.assertLogs(LOGGER_NAME, level="INFO") as logs:
            run_background_worker.run_maintenance()

        self.assertEqual(list(Session.objects.values_list("session_key", flat=True)), ["live".ljust(32, "x")])
        self.assertFalse(SendVerificationChallenge.objects.exists())
        self.assertEqual(
            logs.output,
            [
                f"INFO:{LOGGER_NAME}:Send verification cleanup: expired 0 challenges; deleted 1 challenges "
                "and 0 send requests",
                f"INFO:{LOGGER_NAME}:Cleared 2 expired sessions",
            ],
        )
