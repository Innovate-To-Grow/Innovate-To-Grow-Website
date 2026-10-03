"""Password-login lockout counters under real concurrency: independent PostgreSQL connections, one per worker.

Skipped on SQLite (it serialises writers on one database lock); CI runs these on PostgreSQL.
"""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock, local
from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import patch

from django.core.cache import cache
from django.db import close_old_connections, connection, connections
from django.test import TransactionTestCase

from apps.authn.models import LoginFailureWindow
from apps.authn.services import login_guard
from apps.authn.tests.clock import SECONDS_LEFT_IN_SHORT_WINDOW, FrozenClock

EMAIL = "victim@example.com"
GLOBAL = LoginFailureWindow.GLOBAL_DIGEST


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks and independent transactions")
class LoginGuardPostgresConcurrencyTests(TransactionTestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        # Pin the guard's clock (only the guard's: the driver and pool keep real time) so no window rolls over
        # mid-test; the patch is module-wide, so every worker thread sees the same windows.
        patcher = patch.object(login_guard, "time", SimpleNamespace(time=FrozenClock()))
        patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def parallel(calls):
        barrier = Barrier(len(calls))

        def run(call):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                    cursor.execute("SET statement_timeout = '10s'")
                barrier.wait(timeout=5)
                return call()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=len(calls)) as pool:
            futures = [pool.submit(run, call) for call in calls]
            return [future.result(timeout=30) for future in futures]

    def counts(self):
        return {
            ("global" if digest == GLOBAL else "identifier", window): count
            for digest, window, count in LoginFailureWindow.objects.values_list(
                "identifier_digest", "window", "failure_count"
            )
        }

    def test_simultaneous_failures_for_one_identifier_are_all_counted_and_the_lock_is_logged_once(self):
        workers = 12

        with self.assertLogs("apps.authn.services.login_guard", "WARNING") as logs:
            self.parallel([lambda: login_guard.record_failure(EMAIL)] * workers)

        self.assertEqual(
            self.counts(),
            {("identifier", "15m"): workers, ("identifier", "24h"): workers, ("global", "5m"): workers},
        )
        # Exactly one worker read back the tenth failure, however the twelve interleaved.
        self.assertEqual(
            [record.getMessage().split(" identifier_hash=")[0] for record in logs.records],
            ["Password sign-in locked: window=15m"],
        )
        self.assertEqual(login_guard.retry_after(EMAIL), SECONDS_LEFT_IN_SHORT_WINDOW)

    def test_workers_that_all_miss_a_new_window_race_on_the_insert_without_losing_a_failure(self):
        workers = 6
        real_insert = login_guard._insert_window
        at_insert = Barrier(workers)
        state = local()
        outcomes = []
        outcomes_lock = Lock()

        def insert_together(*args):
            if getattr(state, "raced", False):
                return real_insert(*args)
            state.raced = True
            # Every worker's UPDATE found no row (none can exist before anyone inserts): all INSERT at once.
            at_insert.wait(timeout=5)
            outcome = real_insert(*args)
            with outcomes_lock:
                outcomes.append(outcome)
            return outcome

        with (
            patch.object(login_guard, "_insert_window", side_effect=insert_together),
            self.assertNoLogs("apps.authn.services.login_guard", "WARNING"),
        ):
            self.parallel([lambda: login_guard.record_failure(EMAIL)] * workers)

        self.assertEqual(sorted(outcomes), [False] * (workers - 1) + [True])  # the unique constraint picked one
        self.assertEqual(
            self.counts(),
            {("identifier", "15m"): workers, ("identifier", "24h"): workers, ("global", "5m"): workers},
        )

    def test_a_spray_from_many_workers_is_logged_exactly_once(self):
        workers = 8
        per_worker = login_guard.SPRAY_ALERT_THRESHOLD // workers + 5

        def spray(worker):
            for index in range(per_worker):
                login_guard.record_failure(f"worker{worker}-member{index}@example.com")

        with self.assertLogs("apps.authn.services.login_guard", "WARNING") as logs:
            self.parallel([lambda worker=worker: spray(worker) for worker in range(workers)])

        self.assertEqual(self.counts()[("global", "5m")], workers * per_worker)
        self.assertEqual(
            [record.getMessage() for record in logs.records],
            [
                f"login_guard.failure_spike failures={login_guard.SPRAY_ALERT_THRESHOLD} window=5m "
                f"threshold={login_guard.SPRAY_ALERT_THRESHOLD}"
            ],
        )
