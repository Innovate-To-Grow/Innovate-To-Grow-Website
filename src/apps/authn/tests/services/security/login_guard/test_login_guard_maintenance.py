"""Login guard: purging old windows, password-spray detection, and scoped keys."""

from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.authn.models import LoginFailureWindow
from apps.authn.services.security import login_guard
from apps.authn.tests.helpers.clock import (
    SECONDS_LEFT_IN_DAY,
    SECONDS_LEFT_IN_SHORT_WINDOW,
    SECONDS_LEFT_IN_SPRAY_WINDOW,
)

from .login_guard_helpers import EMAIL, GuardTestCase, at


class PurgeTests(GuardTestCase):
    def windows(self):
        return sorted(LoginFailureWindow.objects.values_list("window", flat=True))

    def test_only_windows_that_have_ended_are_deleted(self):
        self.record(1)
        self.clock.advance(SECONDS_LEFT_IN_SPRAY_WINDOW - 1)
        self.assertEqual(login_guard.purge_expired_failure_windows(), 0)

        self.clock.advance(1)  # the 5-minute window ends now
        self.assertEqual(login_guard.purge_expired_failure_windows(), 1)
        self.assertEqual(self.windows(), ["15m", "24h"])

        self.clock.advance(SECONDS_LEFT_IN_SHORT_WINDOW - SECONDS_LEFT_IN_SPRAY_WINDOW)
        self.assertEqual(login_guard.purge_expired_failure_windows(), 1)
        self.assertEqual(self.windows(), ["24h"])

    def test_purging_never_lifts_a_lock_early(self):
        self.record(30)
        self.clock.advance(SECONDS_LEFT_IN_SHORT_WINDOW)  # the short window has ended, the daily one has not

        self.assertEqual(login_guard.purge_expired_failure_windows(), 2)  # the ended 15m and 5m rows
        self.assertEqual(login_guard.retry_after(EMAIL), SECONDS_LEFT_IN_DAY - SECONDS_LEFT_IN_SHORT_WINDOW)

    def test_an_explicit_now_is_honoured(self):
        self.record(1)

        self.assertEqual(login_guard.purge_expired_failure_windows(now=at(self.clock() + SECONDS_LEFT_IN_DAY)), 3)
        self.assertFalse(LoginFailureWindow.objects.exists())

    def test_rows_are_deleted_in_bounded_batches(self):
        now = self.clock()
        LoginFailureWindow.objects.bulk_create(
            [
                LoginFailureWindow(
                    identifier_digest=f"{index:064x}",
                    window="15m",
                    window_index=index,
                    failure_count=1,
                    expires_at=at(now - index - 1),
                )
                for index in range(7)
            ]
            + [
                LoginFailureWindow(
                    identifier_digest=f"{index:064x}",
                    window="24h",
                    window_index=index,
                    failure_count=1,
                    expires_at=at(now + 60),
                )
                for index in range(2)
            ]
        )

        with CaptureQueriesContext(connection) as queries:
            deleted = login_guard.purge_expired_failure_windows(batch_size=3)

        self.assertEqual(deleted, 7)
        deletes = [query["sql"] for query in queries.captured_queries if query["sql"].startswith("DELETE")]
        self.assertEqual(len(deletes), 3)  # 3 + 3 + 1
        self.assertEqual(self.windows(), ["24h", "24h"])

    def test_nothing_to_purge(self):
        self.assertEqual(login_guard.purge_expired_failure_windows(), 0)

    def make_ended_rows(self, count):
        LoginFailureWindow.objects.bulk_create(
            LoginFailureWindow(
                identifier_digest=f"{index:064x}",
                window="15m",
                window_index=index,
                failure_count=1,
                expires_at=at(self.clock() - index - 1),
            )
            for index in range(count)
        )

    def test_a_stop_request_ends_the_purge_after_the_current_batch(self):
        self.make_ended_rows(8)
        checks = []

        def stop_after_two_batches():
            checks.append(LoginFailureWindow.objects.count())
            return len(checks) > 2

        deleted = login_guard.purge_expired_failure_windows(batch_size=3, should_stop=stop_after_two_batches)

        self.assertEqual(deleted, 6)
        self.assertEqual(checks, [8, 5, 2])  # asked before every batch; each batch was already deleted by then
        self.assertEqual(login_guard.purge_expired_failure_windows(batch_size=3), 2)  # the next run finishes

    def test_a_stop_request_before_the_first_batch_deletes_nothing(self):
        self.make_ended_rows(4)

        with self.assertNumQueries(0):
            self.assertEqual(login_guard.purge_expired_failure_windows(should_stop=lambda: True), 0)

        self.assertEqual(LoginFailureWindow.objects.count(), 4)

    def test_a_stop_check_that_never_fires_changes_nothing(self):
        self.make_ended_rows(7)

        self.assertEqual(login_guard.purge_expired_failure_windows(batch_size=3, should_stop=lambda: False), 7)

    def test_the_batch_size_must_be_positive(self):
        for size in (0, -1):
            with self.subTest(size=size), self.assertRaises(ValueError):
                login_guard.purge_expired_failure_windows(batch_size=size)
