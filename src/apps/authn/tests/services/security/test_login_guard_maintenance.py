"""Login guard: purging old windows, password-spray detection, and scoped keys."""

from unittest.mock import patch

from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext

from apps.authn.models import LoginFailureWindow
from apps.authn.services import login_guard
from apps.authn.tests.clock import (
    SECONDS_LEFT_IN_DAY,
    SECONDS_LEFT_IN_SHORT_WINDOW,
    SECONDS_LEFT_IN_SPRAY_WINDOW,
)

from .login_guard_helpers import (
    EMAIL,
    GLOBAL,
    LOGGER,
    PHONE,
    SCOPE,
    SUBJECT,
    THRESHOLD,
    TYPED_AT_THE_SCOPED_KEY,
    GuardTestCase,
    at,
    identifier_rows,
    spray_count,
)


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
