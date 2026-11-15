from django.test import Client, override_settings
from rest_framework.test import APIClient

from apps.authn.models import LoginFailureWindow
from apps.authn.services import login_guard
from apps.authn.tests.admin.login.password.lockout.test_admin_login_lockout import (
    ALICE,
    DAILY_LIMIT,
    INVALID_EMAIL_OR_PASSWORD,
    LIMIT,
    LOCKED,
    MEMBER_LOGIN_URL,
    OUTSIDE_IP,
    PASSWORD,
    SHORT_WINDOW,
    WRONG,
    AdminLockoutTestCase,
    counted_digests,
)
from apps.authn.views.admin.login.password import REMEMBERED_ADMIN_GUARD_SCOPE, remembered_admin_guard_key
from apps.authn.views.admin.login.state import LAST_ADMIN_LOGIN_COOKIE_NAME


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

    # One client sends about 250 sign-ins in a moment: the request limiter's per-source flood ceiling for sign-in
    # would refuse it first, and this test is about the lockout's counters only.
    @override_settings(REQUEST_RATE_LIMITS_ENABLED=False)
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
