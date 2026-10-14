"""Password login: per-identifier failure lockout (HTTP 429 ``login_locked``); the client IP plays no role.

Ten credential failures in 15 minutes, or thirty in a day, lock the submitted identifier. The lock is checked before
the password is decrypted or hashed, looks identical for existing, unknown and inactive accounts, and is cleared by a
successful sign-in. A site-wide spike of failures (a password spray) is logged once and never refused. Time is frozen
(``apps.authn.tests.clock``) so the windows are exact.
"""

import base64
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITestCase

from apps.authn.models import ContactEmail, ContactPhone, LoginFailureWindow
from apps.authn.services import login_guard
from apps.authn.tests.clock import SECONDS_LEFT_IN_DAY, SECONDS_LEFT_IN_SHORT_WINDOW, freeze_time

Member = get_user_model()

URL = "/authn/login/"
PASSWORD = "LoginPass123!"
WRONG = "TotallyWrong999!"
EMAIL = "student@example.com"
PHONE = "2095551234"

LOCKED_BODY = {
    "detail": "Too many failed sign-in attempts. Please try again later or sign in with an email code.",
    "code": "login_locked",
}
INVALID_BODY = {"non_field_errors": ["Invalid credentials."]}


def rotating_forwarded_for(index):
    return {"HTTP_X_FORWARDED_FOR": f"203.0.113.{index % 250 + 1}, 10.0.0.{index % 250 + 1}"}


# The lockout logic does not depend on the hasher; a fast one keeps dozens of wrong-password checks cheap.
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class LoginLockoutTestCase(APITestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.clock = freeze_time(self)
        self.member = Member.objects.create_user(password=PASSWORD, is_active=True, first_name="Sam", last_name="Lee")
        ContactEmail.objects.create(member=self.member, email_address=EMAIL, email_type="primary", verified=True)
        self.phone_member = Member.objects.create_user(
            password=PASSWORD, is_active=True, first_name="Pat", last_name="Phone"
        )
        ContactPhone.objects.create(member=self.phone_member, phone_number=PHONE, region="1-US", verified=True)

    def login(self, identifier=EMAIL, password=WRONG, field="email", **extra):
        return self.client.post(URL, {field: identifier, "password": password}, format="json", **extra)

    def fail_times(self, times, identifier=EMAIL, **extra):
        return [self.login(identifier, **extra).status_code for _ in range(times)]

    def lock(self, identifier=EMAIL):
        self.assertEqual(self.fail_times(10, identifier), [400] * 10)
        return self.login(identifier)

    def assertLocked(self, response, retry_after=None):
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.data, LOCKED_BODY)
        self.assertIn("Retry-After", response)
        if retry_after is not None:
            self.assertEqual(response["Retry-After"], str(retry_after))


class LockoutThresholdTests(LoginLockoutTestCase):
    def test_the_eleventh_attempt_in_fifteen_minutes_is_locked_with_retry_after(self):
        self.assertEqual(self.fail_times(10), [400] * 10)

        response = self.login()

        self.assertLocked(response, SECONDS_LEFT_IN_SHORT_WINDOW)

    def test_failures_before_the_limit_get_the_plain_invalid_credentials_error(self):
        response = self.login()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, INVALID_BODY)
        self.assertNotIn("Retry-After", response)

    def test_a_correct_password_is_still_refused_while_locked(self):
        self.lock()

        response = self.login(password=PASSWORD)

        self.assertLocked(response)
        self.assertNotIn("access", response.data)

    def test_the_lock_counts_down_and_lifts_when_the_window_ends(self):
        self.lock()
        self.clock.advance(100)
        self.assertLocked(self.login(password=PASSWORD), SECONDS_LEFT_IN_SHORT_WINDOW - 100)

        self.clock.advance(SECONDS_LEFT_IN_SHORT_WINDOW - 100)

        response = self.login(password=PASSWORD)
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)

    def test_failures_while_locked_are_refused_without_extending_the_lock(self):
        self.lock()
        self.clock.advance(200)

        self.assertLocked(self.login(), SECONDS_LEFT_IN_SHORT_WINDOW - 200)
        self.assertLocked(self.login(), SECONDS_LEFT_IN_SHORT_WINDOW - 200)

    def test_thirty_failures_in_a_day_lock_even_when_paced_under_the_short_window(self):
        for _ in range(3):
            self.assertEqual(self.fail_times(9), [400] * 9)
            self.clock.advance(15 * 60)
        self.assertEqual(self.fail_times(3), [400] * 3)

        response = self.login(password=PASSWORD)

        self.assertLocked(response)
        self.assertGreater(int(response["Retry-After"]), 15 * 60)
        self.assertEqual(int(response["Retry-After"]), SECONDS_LEFT_IN_DAY - 3 * 15 * 60)

    def test_the_daily_lock_lifts_at_the_start_of_the_next_day(self):
        for _ in range(3):
            self.assertEqual(self.fail_times(10), [400] * 10)
            self.clock.advance(15 * 60)
        blocked = self.login(password=PASSWORD)
        self.assertLocked(blocked)

        self.clock.advance(int(blocked["Retry-After"]) - 1)
        self.assertLocked(self.login(password=PASSWORD), 1)
        self.clock.advance(1)

        self.assertEqual(self.login(password=PASSWORD).status_code, 200)

    def test_the_identifier_alias_field_is_counted_the_same_way(self):
        statuses = [self.login(field=("identifier" if index % 2 else "email")).status_code for index in range(10)]

        self.assertEqual(statuses, [400] * 10)
        self.assertLocked(self.login(field="identifier"))
        self.assertLocked(self.login(field="email"))

    def test_the_identifier_alias_takes_precedence_over_email_like_validation_does(self):
        body = {"identifier": EMAIL, "email": "decoy@example.com", "password": WRONG}
        for _ in range(10):
            self.client.post(URL, body, format="json")

        self.assertLocked(self.login(EMAIL))
        self.assertEqual(self.login("decoy@example.com").status_code, 400)


class SuccessAndIndependenceTests(LoginLockoutTestCase):
    def test_a_successful_login_clears_the_failure_count(self):
        self.assertEqual(self.fail_times(9), [400] * 9)
        self.assertEqual(self.login(password=PASSWORD).status_code, 200)

        self.assertEqual(self.fail_times(10), [400] * 10)  # would have been locked without the clear
        self.assertLocked(self.login())

    def test_a_successful_login_clears_the_daily_count_too(self):
        for _ in range(2):
            self.assertEqual(self.fail_times(9), [400] * 9)
            self.clock.advance(15 * 60)
        self.assertEqual(self.login(password=PASSWORD).status_code, 200)

        for _ in range(2):
            self.assertEqual(self.fail_times(9), [400] * 9)
            self.clock.advance(15 * 60)
        self.assertEqual(self.login(password=PASSWORD).status_code, 200)

    def test_different_identifiers_are_independent(self):
        self.lock(EMAIL)

        self.assertLocked(self.login(EMAIL, PASSWORD))
        self.assertEqual(self.login(PHONE, PASSWORD).status_code, 200)
        self.assertEqual(self.login("someone-else@example.com").status_code, 400)

    def test_one_identifier_failing_never_touches_the_password_of_another_account(self):
        self.lock(PHONE)

        self.assertEqual(self.login(EMAIL, PASSWORD).status_code, 200)

    def test_phone_formats_share_one_budget(self):
        formats = ["2095551234", "(209) 555-1234", "+1 209 555 1234", "12095551234", "209-555-1234"]
        statuses = [self.login(formats[index % len(formats)]).status_code for index in range(10)]

        self.assertEqual(statuses, [400] * 10)
        for spelling in formats:
            with self.subTest(spelling=spelling):
                self.assertLocked(self.login(spelling, PASSWORD))

    def test_email_case_and_spaces_share_one_budget(self):
        variants = ["student@example.com", "Student@Example.com", "  STUDENT@EXAMPLE.COM ", "student@EXAMPLE.com"]
        statuses = [self.login(variants[index % len(variants)]).status_code for index in range(10)]

        self.assertEqual(statuses, [400] * 10)
        for variant in variants:
            with self.subTest(variant=variant):
                self.assertLocked(self.login(variant, PASSWORD))

    def test_unicode_lookalike_of_an_email_shares_its_budget(self):
        """PostgreSQL ``UPPER()`` resolves ``ſ`` and ``ı`` to ``s`` and ``i``: they must not restart the count."""
        target = "sims.pinar@example.com"
        lookalike = "ſims.pınar@example.com"
        self.assertEqual(self.fail_times(5, target), [400] * 5)
        self.assertEqual(self.fail_times(5, lookalike), [400] * 5)

        self.assertLocked(self.login(target))
        self.assertLocked(self.login(lookalike))


class NoEnumerationOracleTests(LoginLockoutTestCase):
    def setUp(self):
        super().setUp()
        inactive = Member.objects.create_user(password=PASSWORD, is_active=False)
        ContactEmail.objects.create(
            member=inactive, email_address="gone@example.com", email_type="primary", verified=True
        )
        unverified = Member.objects.create_user(password=PASSWORD, is_active=True)
        ContactEmail.objects.create(
            member=unverified, email_address="pending@example.com", email_type="primary", verified=False
        )
        self.identifiers = {
            "existing email": EMAIL,
            "existing phone": PHONE,
            "unknown email": "nobody@example.com",
            "unknown phone": "2025550000",
            "inactive account": "gone@example.com",
            "unverified email": "pending@example.com",
            "not an email or a phone": "just some text",
        }

    def test_locked_responses_are_byte_identical_for_every_kind_of_identifier(self):
        seen = {}
        for label, identifier in self.identifiers.items():
            with self.subTest(identifier=label):
                self.assertEqual(self.fail_times(10, identifier), [400] * 10)
                response = self.login(identifier, PASSWORD)
                seen[label] = (
                    response.status_code,
                    response.content,
                    response["Retry-After"],
                    response["Content-Type"],
                )

        self.assertEqual(len(set(seen.values())), 1, seen)
        self.assertLocked(self.login(EMAIL, PASSWORD), SECONDS_LEFT_IN_SHORT_WINDOW)

    def test_rejections_before_the_limit_are_byte_identical_too(self):
        contents = {label: self.login(identifier).content for label, identifier in self.identifiers.items()}

        self.assertEqual(len(set(contents.values())), 1, contents)

    def test_the_threshold_is_the_same_for_every_kind_of_identifier(self):
        for label, identifier in self.identifiers.items():
            with self.subTest(identifier=label):
                self.assertEqual(self.fail_times(9, identifier), [400] * 9)
                self.assertEqual(self.login(identifier).status_code, 400)
                self.assertEqual(self.login(identifier).status_code, 429)

    def test_daily_lock_is_also_identical_for_known_and_unknown_identifiers(self):
        responses = {}
        for identifier in (EMAIL, "nobody@example.com"):
            for _ in range(3):
                self.assertEqual(self.fail_times(10, identifier), [400] * 10)
                self.clock.advance(15 * 60)
            responses[identifier] = self.login(identifier, PASSWORD)
            self.clock.advance(-3 * 15 * 60)

        first, second = responses.values()
        self.assertLocked(first)
        self.assertEqual(
            (first.status_code, first.content, first["Retry-After"]),
            (second.status_code, second.content, second["Retry-After"]),
        )


class MalformedRequestsAreNotCountedTests(LoginLockoutTestCase):
    def malformed_requests(self):
        undecryptable = base64.b64encode(b"x" * 256).decode()
        return {
            "no password": {"email": EMAIL},
            "blank password": {"email": EMAIL, "password": ""},
            "no identifier": {"password": WRONG},
            "blank identifier": {"email": "   ", "password": WRONG},
            "identifier is a list": {"email": [EMAIL], "password": WRONG},
            "identifier is an object": {"email": {"a": 1}, "password": WRONG},
            "password is a list": {"email": EMAIL, "password": [WRONG]},
            "undecryptable ciphertext": {"email": EMAIL, "password": undecryptable},
        }

    def test_malformed_requests_never_count_or_lock(self):
        for label, body in self.malformed_requests().items():
            with self.subTest(request=label):
                statuses = {self.client.post(URL, body, format="json").status_code for _ in range(15)}

                self.assertEqual(statuses, {400})
        self.assertEqual(self.client.post(URL, [EMAIL], format="json").status_code, 400)
        self.assertEqual(self.client.post(URL, "student", content_type="application/json").status_code, 400)

        # 120+ malformed requests later the account still has its full budget of ten real failures.
        self.assertEqual(self.fail_times(10), [400] * 10)
        self.assertLocked(self.login())

    @override_settings(REQUIRE_ENCRYPTED_PASSWORDS=True)
    def test_plaintext_rejected_by_the_encryption_requirement_is_not_counted(self):
        for _ in range(15):
            response = self.login(password=WRONG)
            self.assertEqual(response.status_code, 400)
            self.assertIn("password", response.data)

        self.assertEqual(self.client.post(URL, {"email": EMAIL, "password": PASSWORD}, format="json").status_code, 400)
        with override_settings(REQUIRE_ENCRYPTED_PASSWORDS=False):
            self.assertEqual(self.fail_times(10), [400] * 10)
            self.assertLocked(self.login())

    def test_a_locked_identifier_answers_a_malformed_request_like_any_other_malformed_request(self):
        self.lock()

        response = self.client.post(URL, {"email": EMAIL}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data, {"password": ["This field is required."]})


class ClientAddressPlaysNoRoleTests(LoginLockoutTestCase):
    def test_failures_from_different_addresses_add_up_for_the_same_identifier(self):
        for index in range(10):
            self.assertEqual(self.login(REMOTE_ADDR=f"198.51.100.{index + 1}").status_code, 400)

        self.assertLocked(self.login(EMAIL, PASSWORD, REMOTE_ADDR="192.0.2.77"))

    def test_a_rotating_forged_forwarded_for_neither_resets_nor_dodges_the_lock(self):
        statuses = [self.login(**rotating_forwarded_for(index)).status_code for index in range(10)]
        self.assertEqual(statuses, [400] * 10)

        for index in range(20, 25):
            self.assertLocked(self.login(EMAIL, PASSWORD, **rotating_forwarded_for(index)))

    def test_the_locked_identifier_is_locked_for_every_address_and_others_are_free_from_the_same_one(self):
        self.lock()

        for address in ("10.0.0.1", "198.51.100.200", "2001:db8::1"):
            with self.subTest(address=address):
                self.assertLocked(self.login(EMAIL, PASSWORD, REMOTE_ADDR=address))
                self.assertEqual(self.login(PHONE, PASSWORD, REMOTE_ADDR=address).status_code, 200)

    def test_one_address_failing_for_many_identifiers_is_never_locked_as_a_whole(self):
        statuses = [self.login(f"user{index}@example.com").status_code for index in range(40)]
        forged = [
            self.login(f"forged{index}@example.com", **rotating_forwarded_for(index)).status_code for index in range(40)
        ]

        self.assertEqual(set(statuses + forged), {400})
        self.assertEqual(self.login(EMAIL, PASSWORD).status_code, 200)

    def test_a_shared_forwarded_for_value_is_not_a_bucket(self):
        """Behind a campus NAT everyone arrives with the same address: each student keeps a separate budget."""
        shared = {"HTTP_X_FORWARDED_FOR": "198.51.100.9"}
        self.lock(EMAIL)

        self.assertEqual(self.login(PHONE, PASSWORD, **shared).status_code, 200)
        self.assertLocked(self.login(EMAIL, PASSWORD, **shared))


class CheckOrderTests(LoginLockoutTestCase):
    def test_a_locked_identifier_costs_one_select_and_no_decrypt_lookup_or_hash(self):
        self.lock()

        with (
            patch("apps.authn.serializers.auth.login.decrypt_field") as decrypt,
            patch("apps.authn.serializers.auth.login.resolve_login_identifier") as resolve,
            patch.object(Member, "check_password") as check,
            CaptureQueriesContext(connection) as queries,
        ):
            response = self.login(password=PASSWORD)

        self.assertLocked(response)
        decrypt.assert_not_called()
        resolve.assert_not_called()
        check.assert_not_called()
        # The lock check itself: one read of the identifier's window rows, and no write.
        self.assertEqual(len(queries.captured_queries), 1, queries.captured_queries)
        sql = queries.captured_queries[0]["sql"]
        self.assertTrue(sql.startswith("SELECT"), sql)
        self.assertIn(LoginFailureWindow._meta.db_table, sql)

    def test_an_unlocked_identifier_does_reach_the_password_check(self):
        with patch.object(Member, "check_password", return_value=False) as check:
            response = self.login()

        self.assertEqual(response.status_code, 400)
        check.assert_called_once()

    def test_a_failure_is_counted_after_the_credential_check_and_a_success_clears_after_it(self):
        with patch.object(Member, "check_password", return_value=False):
            self.fail_times(9)
        with patch.object(Member, "check_password", return_value=True):
            self.assertEqual(self.login().status_code, 200)  # any password: the verifier decides

        with patch.object(Member, "check_password", return_value=False):
            self.assertEqual(self.fail_times(10), [400] * 10)
            self.assertLocked(self.login())


class StoragePrivacyTests(LoginLockoutTestCase):
    def test_no_stored_counter_holds_the_identifier(self):
        self.fail_times(3, "Student@Example.COM")
        self.fail_times(3, "(209) 555-1234")
        self.fail_times(3, "nobody@example.com")

        rows = list(LoginFailureWindow.objects.values())

        self.assertEqual(len(rows), 7)  # three identifiers x two windows, plus the site-wide spray counter
        for row in rows:
            self.assertRegex(row["identifier_digest"], rf"^([0-9a-f]{{64}}|{LoginFailureWindow.GLOBAL_DIGEST})$")
            for value in row.values():
                for fragment in ("student", "nobody", "example", "2095551234"):
                    self.assertNotIn(fragment, str(value).lower())

    def test_the_counters_survive_a_cache_flush(self):
        """Production has no Redis and a per-task file cache: the lockout must not depend on it."""
        self.lock()

        cache.clear()

        self.assertLocked(self.login(password=PASSWORD), SECONDS_LEFT_IN_SHORT_WINDOW)


class SprayDetectionTests(LoginLockoutTestCase):
    """Everyone on campus shares one address: a spray is logged for an alarm, never answered with a lock."""

    def test_a_password_spray_is_logged_once_and_nobody_is_refused(self):
        count = login_guard.SPRAY_ALERT_THRESHOLD + 20
        with self.assertLogs("apps.authn.services.login_guard", "WARNING") as logs:
            statuses = [self.login(f"sprayed{index}@example.com").status_code for index in range(count)]

        self.assertEqual(set(statuses), {400})
        self.assertEqual(len(logs.records), 1)
        message = logs.records[0].getMessage()
        self.assertTrue(message.startswith("login_guard.failure_spike "), message)
        for fragment in ("sprayed", "example", "127.0.0.1"):
            self.assertNotIn(fragment, message)

        # Same address, same minute: members still sign in, and still get their own ten failures.
        self.assertEqual(self.login(EMAIL, PASSWORD).status_code, 200)
        self.assertEqual(self.login(PHONE, PASSWORD).status_code, 200)
        self.assertEqual(self.fail_times(10), [400] * 10)
        self.assertLocked(self.login(EMAIL, PASSWORD))
