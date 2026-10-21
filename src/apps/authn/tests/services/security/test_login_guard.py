"""Login guard: identifier normalization, lockout decisions, storage and counters."""

from unittest.mock import patch

from django.core.cache import cache
from django.db import connection
from django.db.models import signals
from django.dispatch.dispatcher import _make_id
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from apps.authn.models import LoginFailureWindow
from apps.authn.services import login_guard
from apps.authn.tests.clock import (
    DAY_START,
    SECONDS_LEFT_IN_DAY,
    SECONDS_LEFT_IN_SHORT_WINDOW,
    SECONDS_LEFT_IN_SPRAY_WINDOW,
    SECONDS_PER_DAY,
)

from .login_guard_helpers import EMAIL, GLOBAL, LOGGER, PHONE, GuardTestCase, at, identifier_rows, spray_count


class NormalizeIdentifierTests(TestCase):
    def test_email_is_trimmed_and_case_folded(self):
        forms = ["victim@example.com", "  Victim@Example.COM ", "VICTIM@EXAMPLE.COM\n"]

        self.assertEqual({login_guard.normalize_identifier(form) for form in forms}, {"email:victim@example.com"})

    def test_unicode_lookalikes_that_the_database_folds_onto_the_same_email_share_one_identifier(self):
        """PostgreSQL ``UPPER()`` matches ``ſ`` with ``s`` and ``ı`` with ``i``; they must not mint fresh budgets."""
        plain = login_guard.normalize_identifier("pinar.sims@example.com")

        self.assertEqual(login_guard.normalize_identifier("pınar.ſims@example.com"), plain)

    def test_phone_formats_reduce_to_the_national_digits_the_resolver_matches(self):
        forms = ["2095551234", "(209) 555-1234", "+1 209 555 1234", "12095551234", "1-209-555-1234", " 209.555.1234 "]

        self.assertEqual({login_guard.normalize_identifier(form) for form in forms}, {"phone:2095551234"})

    def test_kinds_never_collide(self):
        identifiers = {
            login_guard.normalize_identifier(value) for value in ("2095551234", "2095551234@example.com", "Hello")
        }

        self.assertEqual(len(identifiers), 3)
        self.assertEqual(login_guard.normalize_identifier("HeLLo"), "other:hello")

    def test_the_guard_key_assumes_a_single_phone_region(self):
        """``normalize_identifier`` keys phones on the first region while the resolver tries them all.

        Both agree only while there is one region; when a second is added this fails as a reminder to teach the
        guard about it (otherwise one number could get two budgets).
        """
        from apps.authn.models.contact.phone_regions import PHONE_REGION_CHOICES

        self.assertEqual(len(PHONE_REGION_CHOICES), 1)

    def test_no_identifier(self):
        for value in (None, "", "   ", "\t\n"):
            with self.subTest(value=value):
                self.assertEqual(login_guard.normalize_identifier(value), "")

    def test_numbers_sent_as_json_numbers_are_read_like_the_serializer_reads_them(self):
        self.assertEqual(login_guard.normalize_identifier(2095551234), "phone:2095551234")


class LoginGuardTests(GuardTestCase):
    def test_ten_failures_in_the_short_window_lock_the_identifier_until_that_window_ends(self):
        self.record(9)
        self.assertEqual(login_guard.retry_after(EMAIL), 0)
        login_guard.ensure_not_locked(EMAIL)

        self.record(1)

        self.assertEqual(login_guard.retry_after(EMAIL), SECONDS_LEFT_IN_SHORT_WINDOW)
        with self.assertRaises(login_guard.LoginLocked) as caught:
            login_guard.ensure_not_locked(EMAIL)
        self.assertEqual(caught.exception.retry_after, SECONDS_LEFT_IN_SHORT_WINDOW)

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

    def test_the_tenth_failure_of_a_window_is_logged_with_a_hash_only(self):
        self.record(9)

        with self.assertLogs(LOGGER, "WARNING") as logs:
            self.record(1)

        self.assertEqual(len(logs.records), 1)
        message = logs.records[0].getMessage()
        self.assertIn("window=15m", message)
        self.assertRegex(message, r"identifier_hash=[0-9a-f]{12}$")
        self.assertNotIn("victim", message)

    def test_the_lock_check_is_one_select(self):
        self.record(10)

        with CaptureQueriesContext(connection) as queries:
            self.assertGreater(login_guard.retry_after(EMAIL), 0)

        self.assertEqual(len(queries.captured_queries), 1)
        self.assertTrue(queries.captured_queries[0]["sql"].startswith("SELECT"))

    def test_the_counters_do_not_live_in_the_cache(self):
        """Production has no Redis: a per-task file cache must not hold (or lose) the lockout."""
        self.record(10)

        cache.clear()

        self.assertEqual(login_guard.retry_after(EMAIL), SECONDS_LEFT_IN_SHORT_WINDOW)


class StorageTests(GuardTestCase):
    def test_nothing_references_a_window_and_no_delete_signal_targets_it(self):
        """The raw single-statement deletes rely on this: a new relation or delete receiver must be handled there."""
        self.assertEqual(list(LoginFailureWindow._meta.related_objects), [])
        for signal in (signals.pre_delete, signals.post_delete):
            sender_ids = {lookup_key[1] for lookup_key, *_rest in signal.receivers}
            self.assertNotIn(_make_id(LoginFailureWindow), sender_ids)

    def test_one_row_per_identifier_and_window_plus_one_site_wide_row(self):
        self.record(3, "Victim@Example.com")
        self.record(2, PHONE)

        rows = list(LoginFailureWindow.objects.values_list("identifier_digest", "window", "failure_count"))

        self.assertEqual(len(rows), 5)  # two identifiers x two windows + the spray counter
        self.assertEqual(sorted(count for digest, window, count in rows if digest != GLOBAL), [2, 2, 3, 3])
        self.assertIn((GLOBAL, "5m", 5), rows)

    def test_rows_carry_a_digest_never_the_identifier(self):
        self.record(3, "Victim@Example.com")
        self.record(3, PHONE)
        self.record(3, "just some text")

        for row in LoginFailureWindow.objects.values():
            if row["identifier_digest"] != GLOBAL:
                self.assertRegex(row["identifier_digest"], r"^[0-9a-f]{64}$")
            for value in row.values():
                for fragment in ("victim", "example", "2095551234", "just some text"):
                    self.assertNotIn(fragment, str(value).lower())

    def test_digests_depend_on_the_secret_key(self):
        def digests():
            LoginFailureWindow.objects.all().delete()
            self.record(1)
            return set(identifier_rows().values_list("identifier_digest", flat=True))

        with override_settings(SECRET_KEY="first-secret-for-the-digest"):
            first = digests()
        with override_settings(SECRET_KEY="second-secret-for-the-digest"):
            second = digests()

        self.assertEqual(len(first), 1)
        self.assertTrue(first.isdisjoint(second))

    def test_each_row_expires_when_its_window_ends(self):
        now = self.clock()

        self.record(1)

        self.assertEqual(
            {row.window: row.expires_at for row in LoginFailureWindow.objects.all()},
            {
                "15m": at(now + SECONDS_LEFT_IN_SHORT_WINDOW),
                "24h": at(now + SECONDS_LEFT_IN_DAY),
                "5m": at(now + SECONDS_LEFT_IN_SPRAY_WINDOW),
            },
        )

    def test_window_labels_are_the_models_choices(self):
        labels = {label for label, _length, _limit in login_guard.FAILURE_WINDOWS} | {login_guard.SPRAY_WINDOW[0]}

        self.assertEqual(labels, set(LoginFailureWindow.Window.values))

    def test_a_success_deletes_the_identifiers_rows_but_keeps_the_spray_count(self):
        self.record(4)
        self.record(2, "other@example.com")

        login_guard.clear(EMAIL)

        self.assertEqual(identifier_rows().count(), 2)  # other@example.com's two windows
        self.assertEqual(spray_count(), 6)


class IncrementTests(GuardTestCase):
    DIGEST = "d" * 64

    def increment(self, index=7):
        return login_guard._increment(self.DIGEST, "15m", index, at(self.clock() + 60))

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
        real_insert = login_guard._insert_window
        outcomes = []

        def another_worker_inserts_first(*args):
            if not outcomes:
                self.assertTrue(real_insert(*args))  # the other worker's INSERT lands between our UPDATE and INSERT
            outcome = real_insert(*args)
            outcomes.append(outcome)
            return outcome

        with patch.object(login_guard, "_insert_window", side_effect=another_worker_inserts_first):
            count = self.increment()

        self.assertEqual(outcomes, [False])  # the unique constraint refused the second row
        self.assertEqual(count, 2)
        self.assertEqual(self.count().failure_count, 2)
        self.assertEqual(LoginFailureWindow.objects.count(), 1)

    def test_losing_the_race_to_a_row_that_is_then_cleared_inserts_again(self):
        real_insert = login_guard._insert_window
        calls = []

        def insert_race_then_clear(*args):
            calls.append(args)
            if len(calls) > 1:
                return real_insert(*args)
            real_insert(*args)  # another worker inserts the row
            outcome = real_insert(*args)  # so ours conflicts
            LoginFailureWindow.objects.filter(identifier_digest=self.DIGEST).delete()  # then a success clears it
            return outcome

        with patch.object(login_guard, "_insert_window", side_effect=insert_race_then_clear):
            count = self.increment()

        self.assertEqual((count, len(calls)), (1, 2))
        self.assertEqual(self.count().failure_count, 1)

    def test_an_increment_that_keeps_losing_gives_up_without_an_error(self):
        with patch.object(login_guard, "_insert_window", return_value=False) as insert:
            self.assertEqual(self.increment(), 0)

        self.assertEqual(insert.call_count, login_guard._INCREMENT_ATTEMPTS)

    def test_a_failure_recorded_by_another_worker_between_update_and_insert_still_locks(self):
        """End to end through ``record_failure``: the raced failure is one of the ten that lock."""
        real_insert = login_guard._insert_window
        raced = []

        def race_the_first_short_window_insert(digest, label, index, expires_at):
            if label == "15m" and not raced:
                raced.append(real_insert(digest, label, index, expires_at))
            return real_insert(digest, label, index, expires_at)

        with patch.object(login_guard, "_insert_window", side_effect=race_the_first_short_window_insert):
            self.record(8)  # plus the other worker's failure: nine

        self.assertEqual(raced, [True])
        self.assertEqual(login_guard.retry_after(EMAIL), 0)
        self.record(1)
        self.assertEqual(login_guard.retry_after(EMAIL), SECONDS_LEFT_IN_SHORT_WINDOW)
