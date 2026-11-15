from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.authn.models import LoginFailureWindow
from apps.authn.services.security import login_guard
from apps.authn.tests.helpers.clock import (
    DAY_START,
    SECONDS_LEFT_IN_DAY,
    SECONDS_LEFT_IN_SHORT_WINDOW,
    SECONDS_PER_DAY,
)

from .login_guard_helpers import EMAIL, PHONE, GuardTestCase, at, identifier_rows


class LoginGuardTests(GuardTestCase):
    def test_retry_after_counts_down_and_the_lock_lifts_exactly_when_the_window_ends(self):
        self.record(10)

        self.clock.advance(SECONDS_LEFT_IN_SHORT_WINDOW - 1)
        self.assertEqual(login_guard.retry_after(EMAIL), 1)

        self.clock.advance(1)
        self.assertEqual(login_guard.retry_after(EMAIL), 0)

    def test_more_failures_do_not_extend_the_lock(self):
        self.record(10)
        self.clock.advance(300)

        self.record(3)

        self.assertEqual(login_guard.retry_after(EMAIL), SECONDS_LEFT_IN_SHORT_WINDOW - 300)

    def test_thirty_failures_in_a_day_lock_even_when_paced_under_the_short_window(self):
        for _ in range(3):
            self.record(9)
            self.assertEqual(login_guard.retry_after(EMAIL), 0)
            self.clock.advance(15 * 60)  # a fresh short window every time
        self.record(2)
        self.assertEqual(login_guard.retry_after(EMAIL), 0)

        self.record(1)  # the 30th failure of the day

        self.assertEqual(login_guard.retry_after(EMAIL), DAY_START + SECONDS_PER_DAY - int(self.clock()))
        self.assertGreater(login_guard.retry_after(EMAIL), 15 * 60)

    def test_daily_lock_lifts_at_the_next_day(self):
        for _ in range(3):
            self.record(10)
            self.clock.advance(15 * 60)
        remaining = login_guard.retry_after(EMAIL)
        self.assertGreater(remaining, 15 * 60)

        self.clock.advance(remaining - 1)
        self.assertEqual(login_guard.retry_after(EMAIL), 1)

        self.clock.advance(1)
        self.assertEqual(login_guard.retry_after(EMAIL), 0)
        self.assertEqual(int(self.clock()), DAY_START + SECONDS_PER_DAY)

    def test_the_longer_of_two_active_locks_wins(self):
        self.record(30)

        self.assertEqual(login_guard.retry_after(EMAIL), SECONDS_LEFT_IN_DAY)

    def test_clear_forgets_both_windows(self):
        self.record(9)
        self.clock.advance(15 * 60)
        self.record(9)

        login_guard.clear(EMAIL)
        self.record(9)
        self.assertEqual(login_guard.retry_after(EMAIL), 0)
        self.record(1)

        self.assertGreater(login_guard.retry_after(EMAIL), 0)  # only 10 counted since the clear

    def test_clear_deletes_only_the_current_windows_and_leaves_ended_ones_to_the_purge(self):
        self.record(3)
        self.clock.advance(SECONDS_LEFT_IN_SHORT_WINDOW)  # the first 15-minute window has ended; the day has not
        self.record(2)

        login_guard.clear(EMAIL)

        # The ended 15-minute row is all that is left. It no longer counts, and only the purge removes it.
        self.assertEqual(list(identifier_rows().values_list("window", "failure_count")), [("15m", 3)])
        self.assertEqual(login_guard.retry_after(EMAIL), 0)
        self.record(9)
        self.assertEqual(login_guard.retry_after(EMAIL), 0)  # counting restarted from zero in both windows
        login_guard.purge_expired_failure_windows()
        self.assertFalse(identifier_rows().filter(failure_count=3).exists())

    def test_clear_leaves_yesterdays_rows_to_the_purge(self):
        self.record(4)
        self.clock.advance(SECONDS_LEFT_IN_DAY)  # both of yesterday's windows have ended
        self.record(1)

        login_guard.clear(EMAIL)

        self.assertEqual(sorted(identifier_rows().values_list("window", "failure_count")), [("15m", 4), ("24h", 4)])

    def test_clear_and_the_purge_never_take_the_same_rows(self):
        """What keeps a sign-in and the hourly purge from locking the same rows in opposite orders."""
        self.record(3)
        self.record(3, "other@example.com")
        self.clock.advance(SECONDS_LEFT_IN_SHORT_WINDOW)
        self.record(2)
        before = set(identifier_rows().values_list("pk", flat=True))
        purgeable = set(
            LoginFailureWindow.objects.filter(expires_at__lte=at(self.clock())).values_list("pk", flat=True)
        )

        login_guard.clear(EMAIL)

        cleared = before - set(identifier_rows().values_list("pk", flat=True))
        self.assertEqual(len(cleared), 2)  # the current 15-minute and 24-hour rows of this identifier
        self.assertEqual(len(purgeable & before), 2)  # the ended 15-minute rows of both identifiers
        self.assertEqual(cleared & purgeable, set())

    def test_clear_is_one_delete_limited_to_the_rows_the_lock_check_reads(self):
        self.record(3)

        with CaptureQueriesContext(connection) as queries:
            login_guard.clear(EMAIL)

        self.assertEqual(len(queries.captured_queries), 1)
        statement = queries.captured_queries[0]["sql"]
        self.assertTrue(statement.startswith("DELETE"))
        self.assertIn("window_index", statement)
        self.assertFalse(identifier_rows().exists())

    def test_clear_leaves_other_identifiers_alone(self):
        self.record(10, "one@example.com")
        self.record(10, "two@example.com")

        login_guard.clear("one@example.com")

        self.assertEqual(login_guard.retry_after("one@example.com"), 0)
        self.assertGreater(login_guard.retry_after("two@example.com"), 0)

    def test_identifiers_are_independent(self):
        self.record(10, "one@example.com")

        self.assertGreater(login_guard.retry_after("one@example.com"), 0)
        self.assertEqual(login_guard.retry_after("two@example.com"), 0)
        self.assertEqual(login_guard.retry_after(PHONE), 0)

    def test_equivalent_spellings_share_one_budget(self):
        for spelling in ("2095551234", "(209) 555-1234", "+1 209 555 1234", "12095551234", "209-555-1234"):
            self.record(2, spelling)
        self.record(1, "+12095551234")  # the eleventh failure against one phone number, however it is written

        self.assertGreater(login_guard.retry_after("209 555 1234"), 0)
        self.assertGreater(login_guard.retry_after(PHONE), 0)

        self.record(9, "Victim@Example.com")
        self.assertEqual(login_guard.retry_after(EMAIL), 0)
        self.record(1, "  VICTIM@example.COM ")
        self.assertGreater(login_guard.retry_after(EMAIL), 0)

    def test_a_blank_identifier_is_never_counted_or_locked(self):
        for blank in ("", "   ", None):
            self.record(50, blank)

            self.assertEqual(login_guard.retry_after(blank), 0)
            login_guard.ensure_not_locked(blank)
            login_guard.clear(blank)
        self.assertFalse(LoginFailureWindow.objects.exists())  # not even the site-wide spray counter

    def test_a_failure_recorded_for_one_window_index_does_not_leak_into_the_next(self):
        self.record(10)
        self.clock.advance(SECONDS_LEFT_IN_SHORT_WINDOW)

        self.record(9)

        self.assertEqual(login_guard.retry_after(EMAIL), 0)
