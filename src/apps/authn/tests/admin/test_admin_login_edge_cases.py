"""Edge-case coverage for admin login mixins and helpers."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core import signing
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from apps.authn.models import ContactEmail
from apps.authn.models.security import EmailAuthChallenge
from apps.authn.services import login_guard
from apps.authn.services.email.challenges import AuthChallengeDeliveryError, AuthChallengeThrottled
from apps.authn.views.admin.login_helpers import (
    LAST_ADMIN_LOGIN_COOKIE_NAME,
    get_admin_login_member,
    get_last_admin_login_member,
)

Member = get_user_model()
LOGIN_URL = "/admin/login/"
PURPOSE = EmailAuthChallenge.Purpose.ADMIN_LOGIN


def _signed_cookie_value(value):
    # Mirror how Django signs cookies for get_signed_cookie.
    return signing.get_cookie_signer(salt=LAST_ADMIN_LOGIN_COOKIE_NAME).sign(value)


@override_settings(ROOT_URLCONF="config.routing.urls")
class AdminLoginHelpersTest(TestCase):
    def setUp(self):
        cache.clear()
        self.rf = RequestFactory()
        self.staff = Member.objects.create_user(
            password="testpass123", first_name="Staff", last_name="Admin", is_staff=True, is_active=True
        )
        ContactEmail.objects.create(
            member=self.staff, email_address="admin@example.com", email_type="primary", verified=True
        )

    def test_get_admin_login_member_invalid_uuid_in_session(self):
        request = self.rf.post(LOGIN_URL)
        request.session = {"admin_login_member_id": "not-a-uuid"}
        self.assertIsNone(get_admin_login_member(request))

    def test_get_admin_login_member_no_session(self):
        request = self.rf.post(LOGIN_URL)
        request.session = {}
        self.assertIsNone(get_admin_login_member(request))

    def test_get_last_admin_login_member_invalid_uuid_cookie(self):
        self.client.cookies[LAST_ADMIN_LOGIN_COOKIE_NAME] = _signed_cookie_value("not-a-uuid")
        request = self.rf.get(LOGIN_URL)
        request.COOKIES[LAST_ADMIN_LOGIN_COOKIE_NAME] = _signed_cookie_value("not-a-uuid")
        self.assertIsNone(get_last_admin_login_member(request))

    def test_get_last_admin_login_member_unknown_member(self):
        import uuid

        request = self.rf.get(LOGIN_URL)
        request.COOKIES[LAST_ADMIN_LOGIN_COOKIE_NAME] = _signed_cookie_value(str(uuid.uuid4()))
        self.assertIsNone(get_last_admin_login_member(request))


@override_settings(ROOT_URLCONF="config.routing.urls")
class AdminRememberedPasswordTest(TestCase):
    def setUp(self):
        cache.clear()
        self.staff = Member.objects.create_user(
            password="testpass123", first_name="Staff", last_name="Admin", is_staff=True, is_active=True
        )
        ContactEmail.objects.create(
            member=self.staff, email_address="admin@example.com", email_type="primary", verified=True
        )

    def tearDown(self):
        cache.clear()

    def _set_remembered_cookie(self):
        self.client.cookies[LAST_ADMIN_LOGIN_COOKIE_NAME] = _signed_cookie_value(str(self.staff.pk))

    def test_remembered_password_success(self):
        self._set_remembered_cookie()
        resp = self.client.post(
            LOGIN_URL,
            {"mode": "password", "remembered_admin": "1", "password": "testpass123"},
        )
        self.assertEqual(resp.status_code, 302)

    def test_remembered_password_wrong_password(self):
        self._set_remembered_cookie()
        resp = self.client.post(
            LOGIN_URL,
            {"mode": "password", "remembered_admin": "1", "password": "wrongpass"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Invalid password.")

    def test_remembered_password_invalid_form(self):
        self._set_remembered_cookie()
        resp = self.client.post(
            LOGIN_URL,
            {"mode": "password", "remembered_admin": "1"},  # missing password
        )
        self.assertEqual(resp.status_code, 200)

    def test_remembered_password_no_member_falls_back_to_email(self):
        # No remembered cookie -> get_last_admin_login_member returns None
        resp = self.client.post(
            LOGIN_URL,
            {"mode": "password", "remembered_admin": "1", "password": "testpass123"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Please enter your email to continue.")

    def test_remembered_password_throttled(self):
        self._set_remembered_cookie()
        with patch("apps.authn.views.admin.login.password.login_guard.retry_after", return_value=60) as retry_after:
            resp = self.client.post(
                LOGIN_URL,
                {"mode": "password", "remembered_admin": "1", "password": "testpass123"},
            )
        # The lock is looked up by the member in the signed cookie (a scoped key), not by the client or an email.
        retry_after.assert_called_once_with(login_guard.ScopedKey("admin-remembered", str(self.staff.pk)))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Too many login attempts")


@override_settings(ROOT_URLCONF="config.routing.urls")
class AdminRememberedCodeTest(TestCase):
    def setUp(self):
        cache.clear()
        self.staff = Member.objects.create_user(
            password="testpass123", first_name="Staff", last_name="Admin", is_staff=True, is_active=True
        )
        ContactEmail.objects.create(
            member=self.staff, email_address="admin@example.com", email_type="primary", verified=True
        )

    def tearDown(self):
        cache.clear()

    def _set_remembered_cookie(self, member=None):
        member = member or self.staff
        self.client.cookies[LAST_ADMIN_LOGIN_COOKIE_NAME] = _signed_cookie_value(str(member.pk))

    @patch("apps.authn.views.admin.login.email_code.logging")
    def test_remembered_code_success_sends_code(self, _mock_log):
        self._set_remembered_cookie()
        with patch("apps.authn.views.admin.login.issue_email_challenge") as mock_issue:
            resp = self.client.post(LOGIN_URL, {"action": "remembered_code"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "verification code has been sent")
        mock_issue.assert_called_once()

    def test_remembered_code_no_member_shows_email_step(self):
        # No cookie -> member is None
        resp = self.client.post(LOGIN_URL, {"action": "remembered_code"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Unable to send verification code.")

    def test_remembered_code_throttled(self):
        self._set_remembered_cookie()
        with patch(
            "apps.authn.views.admin.login.issue_email_challenge",
            side_effect=AuthChallengeThrottled("Slow down"),
        ):
            resp = self.client.post(LOGIN_URL, {"action": "remembered_code"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Slow down")

    def _pending_admin_code(self, code="246810"):
        return EmailAuthChallenge.objects.create(
            member=self.staff,
            purpose=PURPOSE,
            target_email="admin@example.com",
            code_hash=make_password(code),
            expires_at=timezone.now() + timezone.timedelta(minutes=10),
            max_attempts=5,
            last_sent_at=timezone.now(),
        )

    def _refused_remembered_code_request(self):
        with patch(
            "apps.authn.views.admin.login.issue_email_challenge",
            side_effect=AuthChallengeThrottled("Please wait before requesting another code."),
        ):
            return self.client.post(LOGIN_URL, {"action": "remembered_code"})

    def test_remembered_code_refused_by_the_address_limits_opens_the_code_step_when_a_code_is_usable(self):
        self._set_remembered_cookie()
        self._pending_admin_code()

        resp = self._refused_remembered_code_request()

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'name="code"')
        self.assertContains(resp, "enter the most recent one below")
        # The remembered flow shows the member's name, never the address.
        self.assertNotContains(resp, "admin@example.com")

    def test_remembered_code_refused_without_a_usable_code_stays_on_the_first_step(self):
        self._set_remembered_cookie()

        resp = self._refused_remembered_code_request()

        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'name="code"')
        self.assertContains(resp, "Please wait before requesting another code.")
        self.assertNotContains(resp, "enter the most recent one below")

    def test_the_address_is_hidden_while_the_first_remembered_send_is_in_flight(self):
        """The state is saved before the mail provider is called; a second tab must not see the address then."""
        self._set_remembered_cookie()
        seen = {}

        def while_sending(**_kwargs):
            seen["hide_email"] = self.client.session.get("admin_login_hide_email")
            seen["page"] = self.client.get(LOGIN_URL).content.decode()

        with patch("apps.authn.views.admin.login.issue_email_challenge", side_effect=while_sending):
            self.client.post(LOGIN_URL, {"action": "remembered_code"})

        self.assertIs(seen["hide_email"], True)
        self.assertIn('name="code"', seen["page"])
        self.assertNotIn("admin@example.com", seen["page"])

    def test_a_typed_address_after_a_remembered_flow_is_shown_again(self):
        self._set_remembered_cookie()
        with patch("apps.authn.views.admin.login.issue_email_challenge"):
            self.client.post(LOGIN_URL, {"action": "remembered_code"})
            self.assertIs(self.client.session["admin_login_hide_email"], True)
            self.client.get(LOGIN_URL + "?step=email")
            self.assertNotIn("admin_login_hide_email", self.client.session)
            typed = self.client.post(LOGIN_URL, {"email": "admin@example.com"})

        self.assertContains(typed, 'name="code"')
        self.assertContains(typed, "admin@example.com")
        self.assertIs(self.client.session["admin_login_hide_email"], False)

    def test_resend_on_the_remembered_code_step_does_not_reveal_the_address(self):
        self._set_remembered_cookie()
        with patch("apps.authn.views.admin.login.issue_email_challenge"):
            first = self.client.post(LOGIN_URL, {"action": "remembered_code"})
            resent = self.client.post(LOGIN_URL, {"action": "resend"})
        self.assertNotContains(first, "admin@example.com")

        self.assertContains(resent, 'name="code"')
        self.assertNotContains(resent, "admin@example.com")

    def test_a_refused_resend_on_the_remembered_code_step_does_not_reveal_the_address(self):
        self._set_remembered_cookie()
        with patch("apps.authn.views.admin.login.issue_email_challenge"):
            self.client.post(LOGIN_URL, {"action": "remembered_code"})
        with patch(
            "apps.authn.views.admin.login.issue_email_challenge",
            side_effect=AuthChallengeThrottled("Please wait before requesting another code."),
        ):
            resent = self.client.post(LOGIN_URL, {"action": "resend"})

        self.assertContains(resent, 'name="code"')
        self.assertNotContains(resent, "admin@example.com")

    def test_remembered_code_delivery_error(self):
        self._set_remembered_cookie()
        with patch(
            "apps.authn.views.admin.login.issue_email_challenge",
            side_effect=AuthChallengeDeliveryError("nope", outcome="permanent"),
        ):
            resp = self.client.post(LOGIN_URL, {"action": "remembered_code"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Failed to send verification code")


@override_settings(ROOT_URLCONF="config.routing.urls")
class AdminCodeStepNoStateTest(TestCase):
    def setUp(self):
        cache.clear()
        self.staff = Member.objects.create_user(
            password="testpass123", first_name="Staff", last_name="Admin", is_staff=True, is_active=True
        )
        ContactEmail.objects.create(
            member=self.staff, email_address="admin@example.com", email_type="primary", verified=True
        )

    def test_get_code_step_renders_when_session_in_code(self):
        # Drive the session into the "code" step, then GET (view.py line 41 branch).
        session = self.client.session
        session["admin_login_step"] = "code"
        session["admin_login_email"] = "admin@example.com"
        session["admin_login_member_id"] = str(self.staff.pk)
        session.save()
        resp = self.client.get(LOGIN_URL)
        self.assertEqual(resp.status_code, 200)
