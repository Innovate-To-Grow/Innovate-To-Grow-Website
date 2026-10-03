import signal
from datetime import timedelta
from io import StringIO
from types import SimpleNamespace
from unittest.mock import call, patch

from django.contrib.sessions.models import Session
from django.db.models.query import QuerySet
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.authn.models import LoginFailureWindow, SendVerificationChallenge
from apps.core.management.commands import run_background_worker
from apps.core.models import BackgroundJob
from apps.core.services.background_jobs import enqueue_job

NOTHING_CLEANED = {"expired_challenges": 0, "deleted_challenges": 0, "deleted_requests": 0}


class RunBackgroundWorkerCommandTests(SimpleTestCase):
    def _run_once(self, *, purged_row_count=0, purged_budget_count=0, batch_size=10):
        command = run_background_worker.Command(stdout=StringIO())
        with (
            patch.object(
                run_background_worker,
                "purge_retired_auth_keypairs",
                return_value=purged_row_count,
            ) as purge,
            patch.object(
                run_background_worker,
                "purge_expired_public_assistant_budgets",
                return_value=purged_budget_count,
            ) as budget_purge,
            patch.object(run_background_worker, "cleanup_expired_records", return_value=NOTHING_CLEANED),
            patch.object(run_background_worker, "clear_expired_sessions", return_value=0),
            patch.object(run_background_worker, "purge_expired_failure_windows", return_value=0),
            patch.object(run_background_worker, "schedule_startup_reconciliation"),
        ):
            command.handle(
                once=True,
                batch_size=batch_size,
                poll_seconds=0.25,
                stale_minutes=10,
                key_purge_seconds=3600,
            )
        return purge, budget_purge

    @patch.object(run_background_worker, "publish_worker_metrics")
    @patch.object(run_background_worker, "worker_metrics", return_value={"heartbeat": 1})
    @patch.object(run_background_worker, "claim_jobs", return_value=[])
    @patch.object(run_background_worker, "recover_stale_jobs")
    def test_worker_runs_retired_key_purge_maintenance(
        self,
        _recover,
        _claim,
        _metrics,
        _publish,
    ):
        with self.assertLogs(run_background_worker.logger, level="INFO") as logs:
            purge, budget_purge = self._run_once(purged_row_count=2)

        purge.assert_called_once_with()
        budget_purge.assert_called_once_with()
        self.assertEqual(
            logs.output, ["INFO:apps.core.management.commands.run_background_worker:Purged retired RSA keypair rows"]
        )

    @patch.object(run_background_worker, "publish_worker_metrics")
    @patch.object(run_background_worker, "worker_metrics", return_value={"heartbeat": 1})
    @patch.object(run_background_worker, "claim_jobs", return_value=[])
    @patch.object(run_background_worker, "recover_stale_jobs")
    def test_worker_purges_expired_public_assistant_budgets(
        self,
        _recover,
        _claim,
        _metrics,
        _publish,
    ):
        with self.assertLogs(run_background_worker.logger, level="INFO") as logs:
            purge, budget_purge = self._run_once(purged_budget_count=2)

        purge.assert_called_once_with()
        budget_purge.assert_called_once_with()
        self.assertEqual(
            logs.output,
            ["INFO:apps.core.management.commands.run_background_worker:Purged expired public assistant budget rows"],
        )

    @patch.object(run_background_worker, "publish_worker_metrics")
    @patch.object(
        run_background_worker,
        "worker_metrics",
        side_effect=RuntimeError("metrics unavailable"),
    )
    @patch.object(run_background_worker, "claim_jobs", return_value=[])
    @patch.object(run_background_worker, "recover_stale_jobs")
    def test_metrics_failure_does_not_terminate_once_cycle(
        self,
        _recover,
        _claim,
        _metrics,
        publish,
    ):
        self._run_once()

        publish.assert_not_called()

    @patch.object(run_background_worker, "publish_worker_metrics")
    @patch.object(
        run_background_worker,
        "worker_metrics",
        return_value={"heartbeat": 1},
    )
    @patch.object(run_background_worker, "process_claimed_job")
    @patch.object(
        run_background_worker,
        "claim_jobs",
        side_effect=[
            [SimpleNamespace(pk=1)],
            [SimpleNamespace(pk=2)],
        ],
    )
    @patch.object(run_background_worker, "recover_stale_jobs")
    def test_job_boundary_failure_does_not_skip_remaining_batch(
        self,
        _recover,
        _claim,
        process,
        _metrics,
        _publish,
    ):
        process.side_effect = [RuntimeError("mirror unavailable"), True]

        self._run_once(batch_size=2)

        self.assertEqual(
            process.call_args_list,
            [call(SimpleNamespace(pk=1)), call(SimpleNamespace(pk=2))],
        )
        self.assertEqual(_claim.call_args_list, [call(batch_size=1), call(batch_size=1)])

    @patch.object(run_background_worker, "publish_worker_metrics")
    @patch.object(
        run_background_worker,
        "worker_metrics",
        return_value={"heartbeat": 1},
    )
    @patch.object(run_background_worker, "process_claimed_job")
    @patch.object(
        run_background_worker,
        "claim_jobs",
        side_effect=[[SimpleNamespace(pk=1)], []],
    )
    @patch.object(run_background_worker, "recover_stale_jobs")
    def test_empty_single_job_claim_stops_the_current_batch(
        self,
        _recover,
        claim,
        process,
        _metrics,
        _publish,
    ):
        self._run_once(batch_size=5)

        process.assert_called_once_with(SimpleNamespace(pk=1))
        self.assertEqual(claim.call_args_list, [call(batch_size=1), call(batch_size=1)])

    @patch.object(run_background_worker, "publish_worker_metrics")
    @patch.object(
        run_background_worker,
        "worker_metrics",
        return_value={"heartbeat": 1},
    )
    @patch.object(run_background_worker, "claim_jobs")
    @patch.object(
        run_background_worker,
        "recover_stale_jobs",
        side_effect=RuntimeError("database temporarily unavailable"),
    )
    def test_maintenance_failure_does_not_terminate_cycle(
        self,
        _recover,
        claim,
        _metrics,
        publish,
    ):
        self._run_once()

        claim.assert_not_called()
        publish.assert_called_once_with({"heartbeat": 1})


class RunBackgroundWorkerStartupTests(SimpleTestCase):
    @override_settings(BACKGROUND_JOBS_ENABLED=False, AMPLIFY_APP_ID="app-123")
    def test_startup_reconciliation_respects_background_jobs_rollout_flag(self):
        with patch(
            "apps.cms.services.amplify.amplify_redirects.schedule_amplify_redirect_sync",
        ) as schedule:
            self.assertFalse(run_background_worker.schedule_startup_reconciliation())

        schedule.assert_not_called()

    @override_settings(BACKGROUND_JOBS_ENABLED=True, AMPLIFY_APP_ID="")
    def test_startup_reconciliation_requires_amplify_app(self):
        with patch(
            "apps.cms.services.amplify.amplify_redirects.schedule_amplify_redirect_sync",
        ) as schedule:
            self.assertFalse(run_background_worker.schedule_startup_reconciliation())

        schedule.assert_not_called()

    @override_settings(BACKGROUND_JOBS_ENABLED=True, AMPLIFY_APP_ID="app-123")
    def test_startup_reconciliation_is_immediate(self):
        with patch(
            "apps.cms.services.amplify.amplify_redirects.schedule_amplify_redirect_sync",
            return_value=SimpleNamespace(pk=1),
        ) as schedule:
            with self.assertLogs(run_background_worker.logger, level="INFO"):
                self.assertTrue(run_background_worker.schedule_startup_reconciliation())

        schedule.assert_called_once_with(immediate=True)

    @override_settings(BACKGROUND_JOBS_ENABLED=True, AMPLIFY_APP_ID="app-123")
    def test_startup_reconciliation_failure_does_not_stop_worker(self):
        with patch(
            "apps.cms.services.amplify.amplify_redirects.schedule_amplify_redirect_sync",
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
            patch.object(run_background_worker, "purge_retired_auth_keypairs", return_value=0),
            patch.object(run_background_worker, "purge_expired_public_assistant_budgets", return_value=0),
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


LOGGER_NAME = "apps.core.management.commands.run_background_worker"


def patch_maintenance(**side_effects):
    """Patch the five maintenance services; ``side_effects`` maps a service name to a side effect."""
    defaults = {
        "purge_retired_auth_keypairs": 0,
        "purge_expired_public_assistant_budgets": 0,
        "cleanup_expired_records": NOTHING_CLEANED,
        "clear_expired_sessions": 0,
        "purge_expired_failure_windows": 0,
    }
    patchers = []
    for name, return_value in defaults.items():
        if name in side_effects:
            patchers.append(patch.object(run_background_worker, name, side_effect=side_effects[name]))
        else:
            patchers.append(patch.object(run_background_worker, name, return_value=return_value))
    return patchers


# The three batched services are called with the stop check; the two single-statement purges take no argument.
BATCHED_SERVICES = ("cleanup_expired_records", "clear_expired_sessions", "purge_expired_failure_windows")


def assert_each_service_ran_once(test_case, mocks, should_stop=None):
    for name, mock in mocks.items():
        if name in BATCHED_SERVICES:
            mock.assert_called_once_with(should_stop=should_stop)
        else:
            mock.assert_called_once_with()


class MaintenanceTaskTests(SimpleTestCase):
    def run_patched(self, **side_effects):
        patchers = patch_maintenance(**side_effects)
        mocks = {}
        for name, patcher in zip(
            (
                "purge_retired_auth_keypairs",
                "purge_expired_public_assistant_budgets",
                "cleanup_expired_records",
                "clear_expired_sessions",
                "purge_expired_failure_windows",
            ),
            patchers,
            strict=True,
        ):
            mocks[name] = patcher.start()
            self.addCleanup(patcher.stop)
        run_background_worker.run_maintenance()
        return mocks

    def test_tasks_run_once_each_in_declared_order(self):
        calls = []

        def record(name, result):
            return lambda **_kwargs: calls.append(name) or result

        self.run_patched(
            purge_retired_auth_keypairs=record("keys", 0),
            purge_expired_public_assistant_budgets=record("assistant budgets", 0),
            cleanup_expired_records=record("send verification", NOTHING_CLEANED),
            clear_expired_sessions=record("sessions", 0),
            purge_expired_failure_windows=record("login failure windows", 0),
        )

        self.assertEqual(calls, ["keys", "assistant budgets", "send verification", "sessions", "login failure windows"])
        self.assertEqual(
            [name for name, _task in run_background_worker.MAINTENANCE_TASKS],
            [
                "Retired RSA key purge",
                "Public assistant budget purge",
                "Send verification cleanup",
                "Expired session cleanup",
                "Login failure window purge",
            ],
        )

    def test_a_failing_task_is_logged_and_every_other_task_still_runs(self):
        with self.assertLogs(LOGGER_NAME, level="INFO") as logs:
            mocks = self.run_patched(
                purge_retired_auth_keypairs=RuntimeError("key store unavailable"),
                cleanup_expired_records=RuntimeError("database temporarily unavailable"),
                clear_expired_sessions=lambda **_kwargs: 3,
            )

        assert_each_service_ran_once(self, mocks)
        self.assertEqual(
            [(record.levelname, record.getMessage(), bool(record.exc_info)) for record in logs.records],
            [
                ("ERROR", "Retired RSA key purge failed", True),
                ("ERROR", "Send verification cleanup failed", True),
                ("INFO", "Cleared 3 expired sessions", False),
            ],
        )

    def test_a_failing_login_window_purge_is_isolated(self):
        with self.assertLogs(LOGGER_NAME, level="INFO") as logs:
            mocks = self.run_patched(
                clear_expired_sessions=lambda **_kwargs: 3,
                purge_expired_failure_windows=RuntimeError("database temporarily unavailable"),
            )

        assert_each_service_ran_once(self, mocks)
        self.assertEqual(
            [(record.levelname, record.getMessage(), bool(record.exc_info)) for record in logs.records],
            [
                ("INFO", "Cleared 3 expired sessions", False),
                ("ERROR", "Login failure window purge failed", True),
            ],
        )

    def test_login_window_purge_runs_after_earlier_failures_and_logs_its_count(self):
        with self.assertLogs(LOGGER_NAME, level="INFO") as logs:
            mocks = self.run_patched(
                purge_retired_auth_keypairs=RuntimeError("key store unavailable"),
                clear_expired_sessions=RuntimeError("session table locked"),
                purge_expired_failure_windows=lambda **_kwargs: 4,
            )

        mocks["purge_expired_failure_windows"].assert_called_once_with(should_stop=None)
        self.assertEqual(
            [(record.levelname, record.getMessage()) for record in logs.records],
            [
                ("ERROR", "Retired RSA key purge failed"),
                ("ERROR", "Expired session cleanup failed"),
                ("INFO", "Purged 4 expired login failure windows"),
            ],
        )

    def test_counts_are_logged_only_when_something_was_cleaned(self):
        cleaned = {"expired_challenges": 2, "deleted_challenges": 3, "deleted_requests": 4}
        with self.assertLogs(LOGGER_NAME, level="INFO") as logs:
            self.run_patched(cleanup_expired_records=lambda **_kwargs: cleaned)

        self.assertEqual(
            logs.output,
            [
                f"INFO:{LOGGER_NAME}:Send verification cleanup: expired 2 challenges; deleted 3 challenges "
                "and 4 send requests"
            ],
        )
        with self.assertNoLogs(LOGGER_NAME, level="INFO"):
            self.run_patched()

    def test_a_stop_request_skips_the_remaining_tasks(self):
        ran = []
        tasks = (
            ("first", lambda _should_stop: ran.append("first")),
            ("second", lambda _should_stop: ran.append("second")),
        )

        run_background_worker.run_maintenance(tasks, should_stop=lambda: bool(ran))

        self.assertEqual(ran, ["first"])

    def test_every_task_is_handed_the_stop_check(self):
        received = []
        tasks = (("first", received.append), ("second", received.append))

        def should_stop():
            return False

        run_background_worker.run_maintenance(tasks, should_stop=should_stop)

        self.assertEqual(received, [should_stop, should_stop])

    def test_the_batched_services_receive_the_workers_stop_check(self):
        patchers = patch_maintenance()
        mocks = {}
        for name, patcher in zip(
            (
                "purge_retired_auth_keypairs",
                "purge_expired_public_assistant_budgets",
                "cleanup_expired_records",
                "clear_expired_sessions",
                "purge_expired_failure_windows",
            ),
            patchers,
            strict=True,
        ):
            mocks[name] = patcher.start()
            self.addCleanup(patcher.stop)

        def should_stop():
            return False

        run_background_worker.run_maintenance(should_stop=should_stop)

        assert_each_service_ran_once(self, mocks, should_stop=should_stop)

    @patch.object(run_background_worker, "publish_worker_metrics")
    @patch.object(run_background_worker, "worker_metrics", return_value={"heartbeat": 1})
    @patch.object(run_background_worker, "claim_jobs", return_value=[])
    @patch.object(run_background_worker, "recover_stale_jobs")
    @patch.object(run_background_worker, "schedule_startup_reconciliation")
    def test_the_worker_cycle_survives_every_task_failing(self, _startup, _recover, claim, _metrics, publish):
        for patcher in patch_maintenance(
            purge_retired_auth_keypairs=RuntimeError("a"),
            purge_expired_public_assistant_budgets=RuntimeError("b"),
            cleanup_expired_records=RuntimeError("c"),
            clear_expired_sessions=RuntimeError("d"),
            purge_expired_failure_windows=RuntimeError("e"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

        with self.assertLogs(LOGGER_NAME, level="ERROR") as logs:
            run_background_worker.Command(stdout=StringIO()).handle(
                once=True, batch_size=1, poll_seconds=0.25, stale_minutes=10, key_purge_seconds=3600
            )

        self.assertEqual(len(logs.output), 5)
        claim.assert_called_once_with(batch_size=1)
        publish.assert_called_once_with({"heartbeat": 1})


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
