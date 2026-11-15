"""Login guard: identifier normalization, lockout decisions, storage and counters."""

from django.db.models import signals
from django.dispatch.dispatcher import _make_id
from django.test import TestCase, override_settings

from apps.authn.models import LoginFailureWindow
from apps.authn.services import login_guard
from apps.authn.tests.helpers.clock import (
    SECONDS_LEFT_IN_DAY,
    SECONDS_LEFT_IN_SHORT_WINDOW,
    SECONDS_LEFT_IN_SPRAY_WINDOW,
)

from .login_guard_helpers import EMAIL, GLOBAL, PHONE, GuardTestCase, at, identifier_rows, spray_count


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
