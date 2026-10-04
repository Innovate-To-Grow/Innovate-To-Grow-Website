"""Identifier-keyed password-login lockout: windows, normalisation, database rows, expiry, purge, spray detection."""

from datetime import UTC, datetime
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
    freeze_time,
)

EMAIL = "victim@example.com"
PHONE = "(209) 555-1234"
GLOBAL = LoginFailureWindow.GLOBAL_DIGEST
THRESHOLD = login_guard.SPRAY_ALERT_THRESHOLD
LOGGER = "apps.authn.services.login_guard"


def at(timestamp: float) -> datetime:
    return datetime.fromtimestamp(timestamp, tz=UTC)


def identifier_rows():
    return LoginFailureWindow.objects.exclude(identifier_digest=GLOBAL)


def spray_count() -> int:
    row = LoginFailureWindow.objects.filter(identifier_digest=GLOBAL).order_by("-window_index").first()
    return row.failure_count if row else 0


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


class GuardTestCase(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.clock = freeze_time(self)

    def record(self, times, identifier=EMAIL):
        for _ in range(times):
            login_guard.record_failure(identifier)


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


class SprayDetectionTests(GuardTestCase):
    """Site-wide failure spikes are logged once per window for an alarm and never refuse anyone."""

    def spray(self, count, start=0):
        for index in range(start, start + count):
            login_guard.record_failure(f"member{index}@example.com")

    @staticmethod
    def spikes(logs):
        return [record for record in logs.records if record.getMessage().startswith("login_guard.failure_spike")]

    def test_one_warning_when_the_site_wide_count_reaches_the_threshold(self):
        with self.assertNoLogs(LOGGER, "WARNING"):
            self.spray(THRESHOLD - 1)

        with self.assertLogs(LOGGER, "WARNING") as logs:
            self.spray(1, start=THRESHOLD - 1)

        self.assertEqual(len(logs.records), 1)
        self.assertEqual(
            logs.records[0].getMessage(),
            f"login_guard.failure_spike failures={THRESHOLD} window=5m threshold={THRESHOLD}",
        )

    def test_the_warning_fires_once_per_window_and_again_in_the_next(self):
        with self.assertLogs(LOGGER, "WARNING") as logs:
            self.spray(THRESHOLD + 50)
        self.assertEqual(len(self.spikes(logs)), 1)
        self.assertEqual(spray_count(), THRESHOLD + 50)

        self.clock.advance(SECONDS_LEFT_IN_SPRAY_WINDOW)
        with self.assertLogs(LOGGER, "WARNING") as logs:
            self.spray(THRESHOLD, start=THRESHOLD + 50)

        self.assertEqual(len(self.spikes(logs)), 1)
        self.assertEqual(spray_count(), THRESHOLD)

    def test_a_spray_never_locks_anyone(self):
        with self.assertLogs(LOGGER, "WARNING"):
            self.spray(THRESHOLD + 50)

        for identifier in ("member0@example.com", f"member{THRESHOLD}@example.com", "fresh@example.com", PHONE):
            with self.subTest(identifier=identifier):
                self.assertEqual(login_guard.retry_after(identifier), 0)
                login_guard.ensure_not_locked(identifier)

    def test_the_warning_names_no_identifier_and_no_digest(self):
        with self.assertLogs(LOGGER, "WARNING") as logs:
            self.spray(THRESHOLD)

        (record,) = self.spikes(logs)
        text = f"{record.getMessage()} {record.args}"
        digests = set(identifier_rows().values_list("identifier_digest", flat=True))
        self.assertEqual(len(digests), THRESHOLD)
        for fragment in ("member", "example", "@", *(digest[:12] for digest in digests)):
            self.assertNotIn(fragment, text)
        self.assertTrue(all(isinstance(arg, (int, str)) and str(arg) in {"5m", str(THRESHOLD)} for arg in record.args))

    def test_failures_against_one_identifier_count_towards_the_spike_too(self):
        with self.assertLogs(LOGGER, "WARNING") as logs:
            self.record(THRESHOLD - 1, "one@example.com")
        self.assertEqual(len(logs.records), 2)  # its own 15-minute and daily locks, no spike yet
        self.assertEqual(self.spikes(logs), [])

        with self.assertLogs(LOGGER, "WARNING") as logs:
            self.record(1, "two@example.com")

        self.assertEqual(len(self.spikes(logs)), 1)

    def test_a_success_does_not_reset_the_site_wide_count(self):
        self.spray(THRESHOLD - 1)
        for index in range(THRESHOLD - 1):
            login_guard.clear(f"member{index}@example.com")

        with self.assertLogs(LOGGER, "WARNING") as logs:
            self.spray(1, start=THRESHOLD)

        self.assertEqual(len(self.spikes(logs)), 1)

    def test_blank_identifiers_are_not_counted(self):
        with self.assertNoLogs(LOGGER, "WARNING"):
            self.record(THRESHOLD + 10, "   ")

        self.assertEqual(spray_count(), 0)


SUBJECT = "0b9c2a4e-5f6d-4c3b-8a1e-2d3f4a5b6c7d"
SCOPE = "admin-remembered"
# What a client could type into an identifier field while aiming at the scoped counter of SUBJECT.
TYPED_AT_THE_SCOPED_KEY = (
    f"{SCOPE}:{SUBJECT}",  # the exact text the scoped key hashes
    f" {SCOPE}:{SUBJECT} ",
    f"{SCOPE}:{SUBJECT}".upper(),
    f"{SCOPE}:{SUBJECT}@",
    f"{SCOPE}:{SUBJECT}@example.com",
    f"admin-member:{SUBJECT}@",
    f"scope:{SCOPE}:{SUBJECT}",
    f"email:{SCOPE}:{SUBJECT}",
    f"phone:{SCOPE}:{SUBJECT}",
    f"other:{SCOPE}:{SUBJECT}",
    f"ScopedKey(scope='{SCOPE}', subject='{SUBJECT}')",
    SUBJECT,
    SUBJECT.replace("-", ""),
    SCOPE,
    f"{SCOPE}:",
    f"{SCOPE}:no digits here",
    "login-guard.scope",
    EMAIL,
    PHONE,
    "+1 209 555 1234",
    "just some text",
    "global",
)


class ScopedKeyTests(GuardTestCase):
    """A ``ScopedKey`` counts like an identifier, in a namespace that no submitted identifier can reach."""

    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        super().setUp()
        self.key = login_guard.ScopedKey(SCOPE, SUBJECT)

    def test_ten_failures_in_the_short_window_lock_the_key_until_that_window_ends(self):
        self.record(9, self.key)
        self.assertEqual(login_guard.retry_after(self.key), 0)
        login_guard.ensure_not_locked(self.key)

        self.record(1, self.key)

        self.assertEqual(login_guard.retry_after(self.key), SECONDS_LEFT_IN_SHORT_WINDOW)
        with self.assertRaises(login_guard.LoginLocked) as caught:
            login_guard.ensure_not_locked(self.key)
        self.assertEqual(caught.exception.retry_after, SECONDS_LEFT_IN_SHORT_WINDOW)

        self.clock.advance(SECONDS_LEFT_IN_SHORT_WINDOW)
        self.assertEqual(login_guard.retry_after(self.key), 0)

    def test_thirty_failures_in_a_day_lock_the_key_until_the_next_day(self):
        for _burst in range(3):
            self.record(10, self.key)
            self.clock.advance(15 * 60)

        self.assertEqual(login_guard.retry_after(self.key), SECONDS_LEFT_IN_DAY - 45 * 60)

        self.clock.advance(SECONDS_LEFT_IN_DAY - 45 * 60)
        self.assertEqual(login_guard.retry_after(self.key), 0)

    def test_no_typed_identifier_has_the_digest_of_the_scoped_key(self):
        for text in TYPED_AT_THE_SCOPED_KEY:
            with self.subTest(typed=text):
                self.assertNotEqual(login_guard._identifier_digest(text), self.key.digest())

    def test_failures_for_typed_identifiers_never_count_against_the_scoped_key(self):
        for text in TYPED_AT_THE_SCOPED_KEY:
            self.record(10, text)
            self.assertGreater(login_guard.retry_after(text), 0)

        self.assertEqual(login_guard.retry_after(self.key), 0)
        self.assertNotIn(self.key.digest(), set(identifier_rows().values_list("identifier_digest", flat=True)))

    def test_failures_for_the_scoped_key_never_count_against_a_typed_identifier(self):
        self.record(10, self.key)

        self.assertGreater(login_guard.retry_after(self.key), 0)
        for text in TYPED_AT_THE_SCOPED_KEY:
            with self.subTest(typed=text):
                self.assertEqual(login_guard.retry_after(text), 0)
        self.assertEqual(set(identifier_rows().values_list("identifier_digest", flat=True)), {self.key.digest()})

    def test_the_separation_does_not_depend_on_what_normalize_identifier_emits(self):
        """The two kinds are HMACs under different keys: even the scoped key's own text, typed, is another row."""
        scoped_text = f"{SCOPE}:{SUBJECT}"

        with patch.object(login_guard, "normalize_identifier", return_value=scoped_text):
            self.assertNotEqual(login_guard._identifier_digest("anything"), self.key.digest())
            self.record(10, "anything")
            self.assertGreater(login_guard.retry_after("anything"), 0)

            self.assertEqual(login_guard.retry_after(self.key), 0)

        self.assertNotEqual(login_guard._HASH_SALT, login_guard._SCOPE_HASH_SALT)
        self.assertNotEqual(login_guard._digest(scoped_text), self.key.digest())

    def test_every_normalised_identifier_is_blank_or_one_of_the_three_typed_kinds(self):
        for text in (*TYPED_AT_THE_SCOPED_KEY, "", "   ", None, 2095551234, "@", ":", "x:y@z", "\tscope:a:b\n"):
            with self.subTest(typed=text):
                self.assertRegex(login_guard.normalize_identifier(text), r"\A(|(email|phone|other):.*)\Z")

    def test_keys_are_independent_per_subject_and_per_scope(self):
        self.record(10, self.key)

        self.assertGreater(login_guard.retry_after(self.key), 0)
        self.assertEqual(login_guard.retry_after(login_guard.ScopedKey(SCOPE, "another-subject")), 0)
        self.assertEqual(login_guard.retry_after(login_guard.ScopedKey("another-scope", SUBJECT)), 0)
        # Equal keys are one counter, whoever built them.
        self.assertEqual(login_guard.ScopedKey(SCOPE, SUBJECT), self.key)
        self.assertGreater(login_guard.retry_after(login_guard.ScopedKey(SCOPE, SUBJECT)), 0)

    def test_scope_and_subject_cannot_run_into_each_other(self):
        # "a" + "b:c" and "a:b" + "c" would hash the same text; a scope may not hold a colon, so only one exists.
        login_guard.ScopedKey("a", "b:c")
        with self.assertRaises(ValueError):
            login_guard.ScopedKey("a:b", "c")

    def test_a_malformed_key_is_an_error_not_an_uncounted_no_op(self):
        for scope in (
            "",
            " ",
            "Admin",
            "admin remembered",
            "admin:remembered",
            "9lives",
            "-a",
            "admin_remembered",
            None,
            5,
        ):
            with self.subTest(scope=scope), self.assertRaises(ValueError):
                login_guard.ScopedKey(scope, SUBJECT)
        for subject in ("", "   ", " padded", "padded ", "padded\n", None, 5, object()):
            with self.subTest(subject=subject), self.assertRaises(ValueError):
                login_guard.ScopedKey(SCOPE, subject)

        self.assertFalse(LoginFailureWindow.objects.exists())

    def test_clear_forgets_the_key_and_nothing_else(self):
        other = login_guard.ScopedKey(SCOPE, "another-subject")
        self.record(10, self.key)
        self.record(10, other)
        self.record(10, EMAIL)

        login_guard.clear(self.key)

        self.assertEqual(login_guard.retry_after(self.key), 0)
        self.assertGreater(login_guard.retry_after(other), 0)
        self.assertGreater(login_guard.retry_after(EMAIL), 0)
        self.assertEqual(spray_count(), 30)

    def test_clearing_a_typed_identifier_leaves_the_scoped_key_locked(self):
        self.record(10, self.key)

        for text in TYPED_AT_THE_SCOPED_KEY:
            login_guard.clear(text)

        self.assertGreater(login_guard.retry_after(self.key), 0)

    def test_failures_count_towards_the_spray_detector(self):
        with self.assertLogs(LOGGER, "WARNING") as logs:
            for index in range(THRESHOLD):
                login_guard.record_failure(login_guard.ScopedKey(SCOPE, f"member-{index}"))

        self.assertEqual(spray_count(), THRESHOLD)
        self.assertEqual(
            [record.getMessage() for record in logs.records],
            [f"login_guard.failure_spike failures={THRESHOLD} window=5m threshold={THRESHOLD}"],
        )

    def test_rows_carry_a_digest_never_the_scope_or_the_subject(self):
        self.record(10, self.key)

        self.assertEqual(LoginFailureWindow.objects.count(), 3)  # two windows + the spray counter
        for row in LoginFailureWindow.objects.values():
            if row["identifier_digest"] != GLOBAL:
                self.assertEqual(row["identifier_digest"], self.key.digest())
                self.assertRegex(row["identifier_digest"], r"^[0-9a-f]{64}$")
            for value in row.values():
                for fragment in (SUBJECT, SUBJECT[:8], SCOPE):
                    self.assertNotIn(fragment, str(value).lower())

    def test_the_lock_is_logged_with_a_hash_only(self):
        self.record(9, self.key)

        with self.assertLogs(LOGGER, "WARNING") as logs:
            self.record(1, self.key)

        (record,) = logs.records
        self.assertEqual(
            record.getMessage(), f"Password sign-in locked: window=15m identifier_hash={self.key.digest()[:12]}"
        )
        self.assertNotIn(SUBJECT[:8], record.getMessage())

    def test_the_digest_depends_on_the_secret_key(self):
        with override_settings(SECRET_KEY="first-secret-for-the-digest"):
            first = self.key.digest()
        with override_settings(SECRET_KEY="second-secret-for-the-digest"):
            second = self.key.digest()

        self.assertNotEqual(first, second)
        self.assertNotEqual(first, GLOBAL)

    def test_the_lock_check_is_one_select(self):
        self.record(10, self.key)

        with CaptureQueriesContext(connection) as queries:
            self.assertGreater(login_guard.retry_after(self.key), 0)

        self.assertEqual(len(queries.captured_queries), 1)
        self.assertTrue(queries.captured_queries[0]["sql"].startswith("SELECT"))
