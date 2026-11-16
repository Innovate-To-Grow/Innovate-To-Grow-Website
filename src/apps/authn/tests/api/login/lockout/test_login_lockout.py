"""Password login: per-identifier failure lockout (HTTP 429 ``login_locked``); the client IP plays no role.

Ten credential failures in 15 minutes, or thirty in a day, lock the submitted identifier. The lock is checked before
the password is decrypted or hashed, looks identical for existing, unknown and inactive accounts, and is cleared by a
successful sign-in. A site-wide spike of failures (a password spray) is logged once and never refused. Time is frozen
(``apps.authn.tests.clock``) so the windows are exact.
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.authn.models import ContactEmail, ContactPhone
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
