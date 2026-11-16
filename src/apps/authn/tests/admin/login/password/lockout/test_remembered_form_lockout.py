from unittest.mock import patch

from django.test import Client

from apps.authn.models import LoginFailureWindow
from apps.authn.services.security import login_guard
from apps.authn.tests.admin.login.password.lockout.test_admin_login_lockout import (
    ALICE,
    BOB,
    DAILY_LIMIT,
    INVALID_EMAIL_OR_PASSWORD,
    INVALID_PASSWORD,
    LIMIT,
    LOCKED,
    LOGIN_URL,
    PASSWORD,
    SHORT_WINDOW,
    AdminLockoutTestCase,
    Member,
    counted_digests,
    make_staff,
    remembered_cookie,
    spray_count,
)
from apps.authn.tests.helpers.clock import SECONDS_LEFT_IN_DAY
from apps.authn.views.admin.login.password import REMEMBERED_ADMIN_GUARD_SCOPE, remembered_admin_guard_key
from apps.authn.views.admin.login.state import LAST_ADMIN_LOGIN_COOKIE_NAME


class RememberedFormLockoutTests(AdminLockoutTestCase):
    def test_the_attempt_after_the_limit_is_locked(self):
        client = self.browser(remembered=self.alice)

        for _ in range(LIMIT):
            self.assertEqual(self.errors(self.remembered_login(client)), [INVALID_PASSWORD])

        response = self.remembered_login(client)
        self.assertEqual(self.errors(response), [LOCKED])
        self.assertContains(response, LOCKED, count=1)
        # The remembered form keeps the address hidden, locked or not.
        self.assertNotContains(response, ALICE)

    def test_a_correct_password_is_refused_while_locked_without_any_password_work(self):
        client = self.lock_remembered_form(self.alice)

        with patch.object(Member, "check_password") as check_password:
            response = self.remembered_login(client, PASSWORD)

        check_password.assert_not_called()
        self.assertEqual(self.errors(response), [LOCKED])
        self.assertNotSignedIn(client)

    def test_two_staff_accounts_on_one_ip_are_independent(self):
        # The reported outage: this form posts no email, so the old (IP, email) key was one bucket for the campus.
        self.lock_remembered_form(self.alice)
        bobs_browser = self.browser(remembered=self.bob)

        self.assertEqual(self.errors(self.remembered_login(bobs_browser)), [INVALID_PASSWORD])
        self.assertSignedIn(bobs_browser, self.remembered_login(bobs_browser, PASSWORD))

    def test_many_staff_typos_on_one_ip_lock_nobody(self):
        staff = [make_staff(f"staff{index}@example.com") for index in range(LIMIT + 2)]

        for member in staff:
            self.assertEqual(self.errors(self.remembered_login(self.browser(remembered=member))), [INVALID_PASSWORD])

        for member in (self.alice, staff[0], staff[-1]):
            client = self.browser(remembered=member)
            self.assertSignedIn(client, self.remembered_login(client, PASSWORD))

    def test_success_clears_the_count(self):
        client = self.browser(remembered=self.alice)
        for _ in range(LIMIT - 1):
            self.remembered_login(client)

        self.assertSignedIn(client, self.remembered_login(client, PASSWORD))

        again = self.browser(remembered=self.alice)
        for _ in range(LIMIT - 1):
            self.assertEqual(self.errors(self.remembered_login(again)), [INVALID_PASSWORD])
        self.assertSignedIn(again, self.remembered_login(again, PASSWORD))

    def test_the_two_forms_count_separately(self):
        # Locking either form leaves the other one open for the same account: neither is a lever on the other.
        remembered = self.lock_remembered_form(self.alice)
        typed = self.browser()
        self.assertSignedIn(typed, self.password_login(typed, ALICE, PASSWORD))

        self.lock_password_form(BOB)
        self.assertEqual(self.errors(self.password_login(self.browser(), BOB, PASSWORD)), [LOCKED])
        bobs_browser = self.browser(remembered=self.bob)
        self.assertSignedIn(bobs_browser, self.remembered_login(bobs_browser, PASSWORD))
        # Alice's remembered form is still locked: Bob's activity, and her own typed sign-in, did not clear it.
        self.assertEqual(self.errors(self.remembered_login(remembered, PASSWORD)), [LOCKED])

    def test_a_success_clears_only_the_counter_of_the_form_that_was_used(self):
        remembered = self.browser(remembered=self.alice)
        typed = self.browser()
        for _ in range(LIMIT - 1):
            self.assertEqual(self.errors(self.remembered_login(remembered)), [INVALID_PASSWORD])
            self.assertEqual(self.errors(self.password_login(typed, ALICE)), [INVALID_EMAIL_OR_PASSWORD])

        self.assertSignedIn(remembered, self.remembered_login(remembered, PASSWORD))

        self.assertEqual(login_guard.retry_after(remembered_admin_guard_key(self.alice)), 0)
        self.assertEqual(counted_digests(), {login_guard.guard._identifier_digest(ALICE)})
        # The typed form kept its nine failures: one more locks it, where a cleared counter would not.
        self.assertEqual(self.errors(self.password_login(typed, ALICE)), [INVALID_EMAIL_OR_PASSWORD])
        self.assertEqual(self.errors(self.password_login(typed, ALICE, PASSWORD)), [LOCKED])

    def test_the_counter_is_the_cookie_members_id_under_a_scope_and_holds_no_client_address(self):
        key = remembered_admin_guard_key(self.alice)
        self.assertEqual(key, login_guard.ScopedKey(REMEMBERED_ADMIN_GUARD_SCOPE, str(self.alice.pk)))
        self.assertEqual(REMEMBERED_ADMIN_GUARD_SCOPE, "admin-remembered")

        # The same cookie from ten different addresses (and forged forwarding chains) is one counter.
        for index in range(LIMIT):
            address = f"203.0.113.{index + 1}"
            client = Client(REMOTE_ADDR=address, HTTP_X_FORWARDED_FOR=f"{address}, 10.0.0.{index + 1}")
            client.cookies[LAST_ADMIN_LOGIN_COOKIE_NAME] = remembered_cookie(self.alice)
            self.assertEqual(self.errors(self.remembered_login(client)), [INVALID_PASSWORD])

        self.assertEqual(self.errors(self.remembered_login(self.browser(remembered=self.alice), PASSWORD)), [LOCKED])
        # One row per window (15 minutes, 24 hours) for that one key, plus the site-wide spray row: no row per IP,
        # and nothing counted under the member's public email.
        self.assertEqual(LoginFailureWindow.objects.count(), 3)
        self.assertEqual(counted_digests(), {key.digest()})
        self.assertNotIn(login_guard.guard._identifier_digest(ALICE), counted_digests())

    def test_thirty_failures_in_a_day_lock_the_form_until_the_next_utc_day(self):
        client = self.browser(remembered=self.alice)
        for _round in range(DAILY_LIMIT // LIMIT):
            for _ in range(LIMIT):
                self.assertEqual(self.errors(self.remembered_login(client)), [INVALID_PASSWORD])
            self.clock.advance(SHORT_WINDOW)  # a fresh 15-minute window: only the daily count carries over

        self.assertEqual(self.errors(self.remembered_login(client, PASSWORD)), [LOCKED])
        self.assertNotSignedIn(client)

        self.clock.advance(SECONDS_LEFT_IN_DAY)
        self.assertSignedIn(client, self.remembered_login(client, PASSWORD))

    def test_failures_count_towards_the_site_wide_spray_detector(self):
        client = self.browser(remembered=self.alice)
        for expected in (1, 2, 3):
            self.remembered_login(client)
            self.assertEqual(spray_count(), expected)

        self.password_login(self.browser(), ALICE)
        self.assertEqual(spray_count(), 4)
        # A success clears the form's own counter and keeps the site-wide one.
        self.assertSignedIn(client, self.remembered_login(client, PASSWORD))
        self.assertEqual(spray_count(), 4)

    def test_a_spray_through_remembered_forms_raises_the_spike_warning(self):
        client = self.browser(remembered=self.alice)
        with (
            patch.object(login_guard.guard, "SPRAY_ALERT_THRESHOLD", 3),
            self.assertLogs("apps.authn.services.login_guard", level="WARNING") as logs,
        ):
            for _ in range(3):
                self.remembered_login(client)

        self.assertEqual(
            [record.getMessage() for record in logs.records],
            ["login_guard.failure_spike failures=3 window=5m threshold=3"],
        )

    def test_a_missing_password_never_counts(self):
        client = self.browser(remembered=self.alice)
        for _ in range(LIMIT + 5):
            response = client.post(LOGIN_URL, {"mode": "password", "remembered_admin": "1"})
            self.assertEqual(response.status_code, 200)

        self.assertFalse(LoginFailureWindow.objects.exists())
        self.assertSignedIn(client, self.remembered_login(client, PASSWORD))

    def test_a_staff_account_without_a_primary_email_is_still_bounded_and_independent(self):
        nameless = make_staff(email=None, first_name="No", last_name="Email")
        other = make_staff(email=None, first_name="Also", last_name="Emailless")
        self.assertEqual(nameless.get_primary_email(), "")

        client = self.lock_remembered_form(nameless)

        self.assertEqual(self.errors(self.remembered_login(client, PASSWORD)), [LOCKED])
        self.assertEqual(counted_digests(), {remembered_admin_guard_key(nameless).digest()})
        others_browser = self.browser(remembered=other)
        self.assertSignedIn(others_browser, self.remembered_login(others_browser, PASSWORD))

    def test_without_a_remembered_member_nothing_is_counted(self):
        client = self.browser()
        for _ in range(LIMIT + 1):
            response = self.remembered_login(client)
            self.assertContains(response, "Please enter your email to continue.")

        self.assertFalse(LoginFailureWindow.objects.exists())
