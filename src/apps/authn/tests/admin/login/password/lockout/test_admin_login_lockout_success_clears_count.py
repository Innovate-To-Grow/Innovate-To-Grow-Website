from apps.authn.models import ContactEmail, LoginFailureWindow
from apps.authn.services import login_guard
from apps.authn.tests.admin.login.password.lockout.test_admin_login_lockout import (
    ALICE,
    INVALID_EMAIL_OR_PASSWORD,
    LIMIT,
    LOCKED,
    LOGIN_URL,
    PASSWORD,
    AdminLockoutTestCase,
    Member,
)
from apps.authn.tests.helpers.clock import SECONDS_LEFT_IN_SHORT_WINDOW


class EmailPasswordFormLockoutTests(AdminLockoutTestCase):
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
