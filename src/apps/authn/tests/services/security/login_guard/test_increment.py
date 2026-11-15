from unittest.mock import patch

from apps.authn.models import LoginFailureWindow
from apps.authn.services.security import login_guard
from apps.authn.tests.helpers.clock import SECONDS_LEFT_IN_SHORT_WINDOW

from .login_guard_helpers import EMAIL, GuardTestCase, at


class IncrementTests(GuardTestCase):
    DIGEST = "d" * 64

    def increment(self, index=7):
        return login_guard.guard._increment(self.DIGEST, "15m", index, at(self.clock() + 60))

    def count(self, index=7):
        return LoginFailureWindow.objects.get(identifier_digest=self.DIGEST, window="15m", window_index=index)

    def test_each_increment_returns_the_rows_new_count(self):
        self.assertEqual([self.increment() for _ in range(5)], [1, 2, 3, 4, 5])
        self.assertEqual(self.count().failure_count, 5)

    def test_another_window_index_gets_its_own_row(self):
        self.increment(7)
        self.increment(7)

        self.assertEqual(self.increment(8), 1)
        self.assertEqual(self.count(7).failure_count, 2)

    def test_losing_the_insert_race_counts_on_top_of_the_winners_row(self):
        """Two workers miss the UPDATE for a new window and both INSERT: the loser must not drop its failure."""
        real_insert = login_guard.counters._insert_window
        outcomes = []

        def another_worker_inserts_first(*args):
            if not outcomes:
                self.assertTrue(real_insert(*args))  # the other worker's INSERT lands between our UPDATE and INSERT
            outcome = real_insert(*args)
            outcomes.append(outcome)
            return outcome

        with patch.object(login_guard.guard, "_insert_window", side_effect=another_worker_inserts_first):
            count = self.increment()

        self.assertEqual(outcomes, [False])  # the unique constraint refused the second row
        self.assertEqual(count, 2)
        self.assertEqual(self.count().failure_count, 2)
        self.assertEqual(LoginFailureWindow.objects.count(), 1)

    def test_losing_the_race_to_a_row_that_is_then_cleared_inserts_again(self):
        real_insert = login_guard.counters._insert_window
        calls = []

        def insert_race_then_clear(*args):
            calls.append(args)
            if len(calls) > 1:
                return real_insert(*args)
            real_insert(*args)  # another worker inserts the row
            outcome = real_insert(*args)  # so ours conflicts
            LoginFailureWindow.objects.filter(identifier_digest=self.DIGEST).delete()  # then a success clears it
            return outcome

        with patch.object(login_guard.guard, "_insert_window", side_effect=insert_race_then_clear):
            count = self.increment()

        self.assertEqual((count, len(calls)), (1, 2))
        self.assertEqual(self.count().failure_count, 1)

    def test_an_increment_that_keeps_losing_gives_up_without_an_error(self):
        with patch.object(login_guard.guard, "_insert_window", return_value=False) as insert:
            self.assertEqual(self.increment(), 0)

        self.assertEqual(insert.call_count, login_guard.guard._INCREMENT_ATTEMPTS)

    def test_a_failure_recorded_by_another_worker_between_update_and_insert_still_locks(self):
        """End to end through ``record_failure``: the raced failure is one of the ten that lock."""
        real_insert = login_guard.counters._insert_window
        raced = []

        def race_the_first_short_window_insert(digest, label, index, expires_at):
            if label == "15m" and not raced:
                raced.append(real_insert(digest, label, index, expires_at))
            return real_insert(digest, label, index, expires_at)

        with patch.object(login_guard.guard, "_insert_window", side_effect=race_the_first_short_window_insert):
            self.record(8)  # plus the other worker's failure: nine

        self.assertEqual(raced, [True])
        self.assertEqual(login_guard.retry_after(EMAIL), 0)
        self.record(1)
        self.assertEqual(login_guard.retry_after(EMAIL), SECONDS_LEFT_IN_SHORT_WINDOW)
