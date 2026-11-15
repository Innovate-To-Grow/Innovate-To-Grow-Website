"""Django-admin password login: per-account failure lockout through ``login_guard``; the client IP plays no role.

Staff share the campus public IP. The old counter was a cache key built from the client IP and the POSTed email, and
the remembered-admin form posts no email, so every staff member on campus shared one bucket: ten typos by anyone
locked that form for all of them. The lockout is now keyed on the account alone and checked before any password
work. The email + password form counts on the submitted email (the counter of the member login). The remembered-admin
form counts on a ``login_guard.ScopedKey`` of the member in the signed cookie, which no typed identifier reaches, so
somebody who merely knows a staff address cannot lock a returning admin's remembered form. The email-code login is
untouched by either. Time is frozen (``apps.authn.tests.helpers.clock``) so a window can never roll over mid-test.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import signing
from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from apps.authn.models import ContactEmail, LoginFailureWindow
from apps.authn.services import login_guard
from apps.authn.tests.helpers.clock import freeze_time
from apps.authn.views.admin.login.state import LAST_ADMIN_LOGIN_COOKIE_NAME

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
