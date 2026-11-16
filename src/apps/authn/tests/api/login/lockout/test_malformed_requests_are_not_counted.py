import base64
from unittest.mock import patch

from django.core.cache import cache
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext

from apps.authn.models import LoginFailureWindow
from apps.authn.tests.api.login.lockout.test_login_lockout import (
    EMAIL,
    PASSWORD,
    PHONE,
    URL,
    WRONG,
    LoginLockoutTestCase,
    Member,
    rotating_forwarded_for,
)
from apps.authn.tests.helpers.clock import SECONDS_LEFT_IN_SHORT_WINDOW


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
