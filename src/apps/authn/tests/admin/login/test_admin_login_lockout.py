"""Django-admin password login: per-account failure lockout through ``login_guard``; the client IP plays no role.

Staff share the campus public IP. The old counter was a cache key built from the client IP and the POSTed email, and
the remembered-admin form posts no email, so every staff member on campus shared one bucket: ten typos by anyone
locked that form for all of them. The lockout is now keyed on the account alone and checked before any password
work. The email + password form counts on the submitted email (the counter of the member login). The remembered-admin
form counts on a ``login_guard.ScopedKey`` of the member in the signed cookie, which no typed identifier reaches, so
somebody who merely knows a staff address cannot lock a returning admin's remembered form. The email-code login is
untouched by either. Time is frozen (``apps.authn.tests.clock``) so a window can never roll over mid-test.
"""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core import signing
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.authn.models import ContactEmail, LoginFailureWindow
from apps.authn.models.security import EmailAuthChallenge
from apps.authn.services import login_guard
from apps.authn.tests.clock import SECONDS_LEFT_IN_DAY, SECONDS_LEFT_IN_SHORT_WINDOW, freeze_time
from apps.authn.views.admin.login.password import REMEMBERED_ADMIN_GUARD_SCOPE, remembered_admin_guard_key
from apps.authn.views.admin.login_helpers import LAST_ADMIN_LOGIN_COOKIE_NAME

Member = get_user_model()

LOGIN_URL = "/admin/login/"
MEMBER_LOGIN_URL = "/authn/login/"
PASSWORD = "AdminPass123!"
WRONG = "TotallyWrong999!"
ALICE = "alice.admin@example.com"
BOB = "bob.admin@example.com"
CAMPUS_IP = "169.236.0.10"
OUTSIDE_IP = "198.51.100.7"

LIMIT = login_guard.FAILURE_WINDOWS[0][2]
SHORT_WINDOW = login_guard.FAILURE_WINDOWS[0][1]
DAILY_LIMIT = login_guard.FAILURE_WINDOWS[1][2]
GLOBAL = LoginFailureWindow.GLOBAL_DIGEST
LOCKED = "Too many login attempts. Please try again later."
INVALID_EMAIL_OR_PASSWORD = "Invalid email or password."
INVALID_PASSWORD = "Invalid password."


def make_staff(email, **extra):
    member = Member.objects.create_user(password=PASSWORD, is_staff=True, is_active=True, **extra)
    if email:
        ContactEmail.objects.create(member=member, email_address=email, email_type="primary", verified=True)
    return member


def remembered_cookie(member):
    return signing.get_cookie_signer(salt=LAST_ADMIN_LOGIN_COOKIE_NAME).sign(str(member.pk))


def counted_digests():
    """Digests of every per-account counter that exists (the site-wide spray row excluded)."""
    return set(LoginFailureWindow.objects.exclude(identifier_digest=GLOBAL).values_list("identifier_digest", flat=True))


def spray_count():
    row = LoginFailureWindow.objects.filter(identifier_digest=GLOBAL).order_by("-window_index").first()
    return row.failure_count if row else 0


# The lockout logic does not depend on the hasher; a fast one keeps dozens of wrong-password checks cheap.
@override_settings(
    ROOT_URLCONF="config.routing.urls",
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class AdminLockoutTestCase(TestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.clock = freeze_time(self)
        self.alice = make_staff(ALICE, first_name="Alice", last_name="Admin")
        self.bob = make_staff(BOB, first_name="Bob", last_name="Admin")

    def browser(self, remembered=None):
        """A separate browser on the campus network, optionally carrying a member's remembered-admin cookie."""
        client = Client(REMOTE_ADDR=CAMPUS_IP, HTTP_X_FORWARDED_FOR=CAMPUS_IP)
        if remembered is not None:
            client.cookies[LAST_ADMIN_LOGIN_COOKIE_NAME] = remembered_cookie(remembered)
        return client

    @staticmethod
    def password_login(client, email, password=WRONG, **extra):
        return client.post(LOGIN_URL, {"mode": "password", "email": email, "password": password}, **extra)

    @staticmethod
    def remembered_login(client, password=WRONG, **extra):
        return client.post(LOGIN_URL, {"mode": "password", "remembered_admin": "1", "password": password}, **extra)

    @staticmethod
    def errors(response):
        if response.status_code != 200:
            return [f"status {response.status_code}"]
        return list(response.context["form"].non_field_errors())

    def assertSignedIn(self, client, response):
        self.assertRedirects(response, "/admin/", fetch_redirect_response=False)
        self.assertEqual(client.get("/admin/").status_code, 200)

    def assertNotSignedIn(self, client):
        self.assertEqual(client.get("/admin/").status_code, 302)

    def lock_password_form(self, email, client=None):
        client = client or self.browser()
        for _ in range(LIMIT):
            self.assertEqual(self.errors(self.password_login(client, email)), [INVALID_EMAIL_OR_PASSWORD])
        self.assertEqual(self.errors(self.password_login(client, email)), [LOCKED])

    def lock_remembered_form(self, member):
        client = self.browser(remembered=member)
        for _ in range(LIMIT):
            self.assertEqual(self.errors(self.remembered_login(client)), [INVALID_PASSWORD])
        self.assertEqual(self.errors(self.remembered_login(client)), [LOCKED])
        return client


class EmailPasswordFormLockoutTests(AdminLockoutTestCase):
    def test_the_attempt_after_the_limit_is_locked(self):
        client = self.browser()

        for _ in range(LIMIT):
            response = self.password_login(client, ALICE)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.errors(response), [INVALID_EMAIL_OR_PASSWORD])

        response = self.password_login(client, ALICE)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.errors(response), [LOCKED])
        self.assertContains(response, LOCKED, count=1)

    def test_a_correct_password_is_refused_while_locked_without_any_password_work(self):
        self.lock_password_form(ALICE)
        client = self.browser()

        with patch("apps.authn.views.admin.login.password.authenticate") as authenticate:
            response = self.password_login(client, ALICE, PASSWORD)

        authenticate.assert_not_called()
        self.assertEqual(self.errors(response), [LOCKED])
        self.assertNotSignedIn(client)
        self.assertNotIn(LAST_ADMIN_LOGIN_COOKIE_NAME, response.cookies)

    def test_two_staff_accounts_on_one_ip_are_independent(self):
        self.lock_password_form(ALICE)
        client = self.browser()

        self.assertEqual(self.errors(self.password_login(client, BOB)), [INVALID_EMAIL_OR_PASSWORD])
        self.assertSignedIn(client, self.password_login(client, BOB, PASSWORD))

    def test_rotating_the_client_ip_does_not_buy_more_guesses(self):
        for index in range(LIMIT):
            address = f"203.0.113.{index + 1}"
            client = Client(REMOTE_ADDR=address, HTTP_X_FORWARDED_FOR=f"{address}, 10.0.0.{index + 1}")
            self.assertEqual(self.errors(self.password_login(client, ALICE)), [INVALID_EMAIL_OR_PASSWORD])

        fresh = Client(REMOTE_ADDR="198.51.100.77", HTTP_X_FORWARDED_FOR="198.51.100.77")
        self.assertEqual(self.errors(self.password_login(fresh, ALICE, PASSWORD)), [LOCKED])
        # One account, one row per window (15 minutes, 24 hours) plus the site-wide spray counter: no row per IP.
        self.assertEqual(LoginFailureWindow.objects.count(), 3)

    def test_the_same_address_in_another_case_or_padded_is_one_account(self):
        client = self.browser()
        variants = ["Alice.Admin@Example.COM", "  alice.admin@example.com  ", ALICE.upper(), ALICE]
        for index in range(LIMIT):
            response = self.password_login(client, variants[index % len(variants)])
            self.assertEqual(self.errors(response), [INVALID_EMAIL_OR_PASSWORD])

        self.assertEqual(self.errors(self.password_login(client, ALICE, PASSWORD)), [LOCKED])

    def test_success_clears_the_count(self):
        client = self.browser()
        for _ in range(LIMIT - 1):
            self.password_login(client, ALICE)

        self.assertSignedIn(client, self.password_login(client, ALICE, PASSWORD))
        self.assertFalse(
            LoginFailureWindow.objects.exclude(identifier_digest=LoginFailureWindow.GLOBAL_DIGEST).exists()
        )

        # A fresh budget: nine more failures and a success, where an uncleared count would have locked at the first.
        again = self.browser()
        for _ in range(LIMIT - 1):
            self.assertEqual(self.errors(self.password_login(again, ALICE)), [INVALID_EMAIL_OR_PASSWORD])
        self.assertSignedIn(again, self.password_login(again, ALICE, PASSWORD))

    def test_an_unknown_email_behaves_exactly_like_a_known_one(self):
        known = [self.errors(self.password_login(self.browser(), ALICE)) for _ in range(LIMIT + 2)]
        unknown = [self.errors(self.password_login(self.browser(), "nobody@example.com")) for _ in range(LIMIT + 2)]

        self.assertEqual(known, [[INVALID_EMAIL_OR_PASSWORD]] * LIMIT + [[LOCKED]] * 2)
        self.assertEqual(unknown, known)

    def test_a_non_staff_account_counts_and_locks_like_any_other(self):
        regular = Member.objects.create_user(password=PASSWORD, is_staff=False, is_active=True)
        ContactEmail.objects.create(
            member=regular, email_address="regular@example.com", email_type="primary", verified=True
        )
        client = self.browser()

        # The right password of a non-staff account is still a refused admin sign-in.
        attempts = [self.errors(self.password_login(client, "regular@example.com", PASSWORD)) for _ in range(LIMIT + 1)]

        self.assertEqual(attempts, [[INVALID_EMAIL_OR_PASSWORD]] * LIMIT + [[LOCKED]])

    def test_a_malformed_submission_never_counts(self):
        client = self.browser()
        for _ in range(LIMIT + 5):
            self.assertEqual(client.post(LOGIN_URL, {"mode": "password", "email": ALICE}).status_code, 200)
            self.assertEqual(client.post(LOGIN_URL, {"mode": "password", "email": "not-an-email"}).status_code, 200)

        self.assertFalse(LoginFailureWindow.objects.exists())
        self.assertSignedIn(client, self.password_login(client, ALICE, PASSWORD))

    def test_the_lock_lifts_when_the_window_ends(self):
        self.lock_password_form(ALICE)
        self.clock.advance(SECONDS_LEFT_IN_SHORT_WINDOW - 1)
        self.assertEqual(self.errors(self.password_login(self.browser(), ALICE, PASSWORD)), [LOCKED])

        self.clock.advance(1)

        client = self.browser()
        self.assertSignedIn(client, self.password_login(client, ALICE, PASSWORD))

    def test_the_member_api_login_and_the_admin_form_share_one_budget_per_account(self):
        # Same identifier, same guard: failures on the SPA password login count against the admin form too, so an
        # attacker does not get one allowance per entry point.
        for _ in range(LIMIT):
            login_guard.record_failure(ALICE)

        self.assertEqual(self.errors(self.password_login(self.browser(), ALICE, PASSWORD)), [LOCKED])


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
        self.assertEqual(counted_digests(), {login_guard._identifier_digest(ALICE)})
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
        self.assertNotIn(login_guard._identifier_digest(ALICE), counted_digests())

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
            patch.object(login_guard, "SPRAY_ALERT_THRESHOLD", 3),
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


class RemoteLockoutOfTheRememberedFormTests(AdminLockoutTestCase):
    """Knowing a staff address is not enough to lock that person's remembered form: that takes the signed cookie.

    The attacker is off campus, has no cookie, and fails on purpose wherever an identifier can be typed. That locks
    the counters of those typed identifiers (by design: the address is all an anonymous request can be counted by).
    The remembered form of the victim, who is on the campus IP with the cookie, must keep working throughout.
    """

    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        super().setUp()
        self.attacker_admin = Client(REMOTE_ADDR=OUTSIDE_IP, HTTP_X_FORWARDED_FOR=OUTSIDE_IP)
        self.attacker_api = APIClient(REMOTE_ADDR=OUTSIDE_IP, HTTP_X_FORWARDED_FOR=OUTSIDE_IP)

    def member_login(self, identifier, password=WRONG, field="email"):
        return self.attacker_api.post(MEMBER_LOGIN_URL, {field: identifier, "password": password}, format="json")

    def assertRememberedFormUntouched(self, member):
        self.assertEqual(login_guard.retry_after(remembered_admin_guard_key(member)), 0)
        self.assertNotIn(remembered_admin_guard_key(member).digest(), counted_digests())
        victim = self.browser(remembered=member)
        self.assertSignedIn(victim, self.remembered_login(victim, PASSWORD))

    def test_thirty_wrong_passwords_on_the_member_login_do_not_lock_the_remembered_form(self):
        for _round in range(DAILY_LIMIT // LIMIT):
            for _ in range(LIMIT):
                response = self.member_login(ALICE)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.data, {"non_field_errors": ["Invalid credentials."]})
            self.clock.advance(SHORT_WINDOW)

        # The attack worked on what it can reach: the address is locked for the day on every typed entry point.
        response = self.member_login(ALICE, PASSWORD)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.data["code"], "login_locked")
        self.assertEqual(self.errors(self.password_login(self.browser(), ALICE, PASSWORD)), [LOCKED])
        # And it did not reach the remembered form.
        self.assertRememberedFormUntouched(self.alice)

    def test_thirty_wrong_passwords_on_the_admin_email_form_do_not_lock_the_remembered_form(self):
        for _round in range(DAILY_LIMIT // LIMIT):
            for _ in range(LIMIT):
                self.assertEqual(
                    self.errors(self.password_login(self.attacker_admin, ALICE)), [INVALID_EMAIL_OR_PASSWORD]
                )
            self.clock.advance(SHORT_WINDOW)

        self.assertEqual(self.errors(self.password_login(self.browser(), ALICE, PASSWORD)), [LOCKED])
        self.assertEqual(self.member_login(ALICE, PASSWORD).status_code, 429)
        self.assertRememberedFormUntouched(self.alice)

    def test_the_remembered_form_keeps_working_while_the_attack_is_running(self):
        # Inside one 15-minute window, with the address freshly locked and the attacker still posting.
        for _ in range(LIMIT):
            self.member_login(ALICE)
            self.password_login(self.attacker_admin, ALICE)
        self.assertEqual(self.member_login(ALICE).status_code, 429)
        self.assertEqual(self.errors(self.password_login(self.attacker_admin, ALICE)), [LOCKED])

        self.assertRememberedFormUntouched(self.alice)

    def test_posting_the_remembered_form_without_the_cookie_counts_nothing(self):
        for _ in range(DAILY_LIMIT):
            response = self.remembered_login(self.attacker_admin)
            self.assertContains(response, "Please enter your email to continue.")
        # A cookie the attacker made up (not signed by this server) is no cookie.
        self.attacker_admin.cookies[LAST_ADMIN_LOGIN_COOKIE_NAME] = f"{self.alice.pk}:forged:signature"
        for _ in range(LIMIT + 1):
            response = self.remembered_login(self.attacker_admin)
            self.assertContains(response, "Please enter your email to continue.")

        self.assertFalse(LoginFailureWindow.objects.exists())
        self.assertRememberedFormUntouched(self.alice)

    def test_no_typed_identifier_reaches_the_remembered_counter(self):
        key = remembered_admin_guard_key(self.alice)
        pk = self.alice.pk
        typed = [
            f"{REMEMBERED_ADMIN_GUARD_SCOPE}:{pk}",  # the exact text the scoped key hashes
            f"{REMEMBERED_ADMIN_GUARD_SCOPE}:{pk}@",
            f"{REMEMBERED_ADMIN_GUARD_SCOPE}:{pk}@example.com",
            f'"{REMEMBERED_ADMIN_GUARD_SCOPE}:{pk}"@example.com',  # a quoted local part passes the email field
            f"admin-member:{pk}@",  # the fallback identifier this form once used
            f"scope:{REMEMBERED_ADMIN_GUARD_SCOPE}:{pk}",
            f"email:{REMEMBERED_ADMIN_GUARD_SCOPE}:{pk}",
            f"other:{REMEMBERED_ADMIN_GUARD_SCOPE}:{pk}",
            f"ScopedKey(scope='{REMEMBERED_ADMIN_GUARD_SCOPE}', subject='{pk}')",
            str(pk),
            pk.hex,
            key.digest(),
            REMEMBERED_ADMIN_GUARD_SCOPE,
            ALICE,
        ]

        for text in typed:
            with self.subTest(typed=text):
                # Enough failures to lock whatever counter the text maps to, on every entry point that takes one.
                for field in ("email", "identifier"):
                    for _ in range(LIMIT + 1):
                        self.assertIn(self.member_login(text, field=field).status_code, (400, 429))
                for _ in range(LIMIT + 1):
                    self.assertEqual(self.password_login(self.attacker_admin, text).status_code, 200)

                self.assertEqual(login_guard.retry_after(key), 0)
                self.assertNotIn(key.digest(), counted_digests())

        # The typed texts did get counted (under their own identifiers), so the loop above was not vacuous.
        self.assertGreaterEqual(len(counted_digests()), 5)
        self.assertEqual(self.member_login(typed[0]).status_code, 429)
        self.assertEqual(self.errors(self.password_login(self.attacker_admin, typed[3])), [LOCKED])
        self.assertRememberedFormUntouched(self.alice)


class EmailCodeLoginWhileLockedTests(AdminLockoutTestCase):
    """The lockout is on passwords only: a locked admin can still sign in with an email code."""

    def _pending_challenge(self, member, email):
        return EmailAuthChallenge.objects.create(
            member=member,
            purpose=EmailAuthChallenge.Purpose.ADMIN_LOGIN,
            target_email=email,
            code_hash=make_password("654321"),
            expires_at=timezone.now() + timedelta(minutes=10),
            max_attempts=5,
            last_sent_at=timezone.now(),
        )

    def test_the_typed_email_code_flow_signs_in_a_locked_admin(self):
        self.lock_password_form(ALICE)
        client = self.browser()

        with patch("apps.authn.views.admin.login.issue_email_challenge") as issue:
            response = client.post(LOGIN_URL, {"email": ALICE})
        issue.assert_called_once()
        self.assertContains(response, 'name="code"')

        challenge = self._pending_challenge(self.alice, ALICE)
        with patch("apps.authn.views.admin.login.verify_email_code", return_value=challenge):
            response = client.post(LOGIN_URL, {"code": "654321"})

        self.assertSignedIn(client, response)
        # Signing in by code proves nothing about the password, so the password lock stays until its window ends.
        self.assertEqual(self.errors(self.password_login(self.browser(), ALICE, PASSWORD)), [LOCKED])

    def test_the_remembered_email_code_flow_signs_in_a_locked_admin(self):
        client = self.lock_remembered_form(self.alice)

        with patch("apps.authn.views.admin.login.issue_email_challenge") as issue:
            response = client.post(LOGIN_URL, {"action": "remembered_code"})
        issue.assert_called_once()
        self.assertContains(response, 'name="code"')

        challenge = self._pending_challenge(self.alice, ALICE)
        with patch("apps.authn.views.admin.login.verify_email_code", return_value=challenge):
            response = client.post(LOGIN_URL, {"code": "654321"})

        self.assertSignedIn(client, response)

    def test_the_locked_page_still_offers_the_email_code_login(self):
        client = self.lock_remembered_form(self.alice)

        response = self.remembered_login(client, PASSWORD)

        self.assertContains(response, LOCKED)
        self.assertContains(response, "Send verification code instead")
