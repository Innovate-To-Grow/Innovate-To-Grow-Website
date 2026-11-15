from unittest.mock import patch

from apps.authn.models import LoginFailureWindow
from apps.authn.services import login_guard
from apps.authn.tests.helpers.clock import SECONDS_LEFT_IN_DAY, SECONDS_LEFT_IN_SHORT_WINDOW

from ..login_guard.login_guard_helpers import (
    EMAIL,
    GLOBAL,
    LOGGER,
    SCOPE,
    SUBJECT,
    THRESHOLD,
    TYPED_AT_THE_SCOPED_KEY,
    GuardTestCase,
    identifier_rows,
    spray_count,
)


class _ScopedKeyCase(GuardTestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        super().setUp()
        self.key = login_guard.ScopedKey(SCOPE, SUBJECT)


class ScopedKeyTests(_ScopedKeyCase):
    """A ``ScopedKey`` counts like an identifier, in a namespace that no submitted identifier can reach."""

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
                self.assertNotEqual(login_guard.guard._identifier_digest(text), self.key.digest())

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

        with patch.object(login_guard.guard, "normalize_identifier", return_value=scoped_text):
            self.assertNotEqual(login_guard.guard._identifier_digest("anything"), self.key.digest())
            self.record(10, "anything")
            self.assertGreater(login_guard.retry_after("anything"), 0)

            self.assertEqual(login_guard.retry_after(self.key), 0)

        self.assertNotEqual(login_guard.counters._HASH_SALT, login_guard.counters._SCOPE_HASH_SALT)
        self.assertNotEqual(login_guard.counters._digest(scoped_text), self.key.digest())

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
