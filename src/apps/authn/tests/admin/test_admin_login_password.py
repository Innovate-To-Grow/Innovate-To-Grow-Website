"""Tests ensuring the admin password-only login path stays disabled."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.authn.models import ContactEmail
from apps.authn.models.security import EmailAuthChallenge
from apps.authn.views.admin.login_helpers import LAST_ADMIN_LOGIN_COOKIE_NAME, set_last_admin_login_cookie

Member = get_user_model()
LOGIN_URL = "/admin/login/"
PURPOSE = EmailAuthChallenge.Purpose.ADMIN_LOGIN


def _create_pending_challenge(member, email, code="123456"):
    return EmailAuthChallenge.objects.create(
        member=member,
        purpose=PURPOSE,
        target_email=email,
        code_hash=make_password(code),
        expires_at=timezone.now() + timedelta(minutes=10),
        max_attempts=5,
        last_sent_at=timezone.now(),
    )


def _last_admin_cookie_value(member):
    from django.http import HttpResponse

    response = HttpResponse()
    set_last_admin_login_cookie(response, member)
    return response.cookies[LAST_ADMIN_LOGIN_COOKIE_NAME].value


@override_settings(ROOT_URLCONF="config.urls")
class AdminPasswordLoginDisabledTest(TestCase):
    def setUp(self):
        cache.clear()
        self.staff = Member.objects.create_user(password="testpass123", is_staff=True, is_active=True)
        ContactEmail.objects.create(
            member=self.staff, email_address="admin@example.com", email_type="primary", verified=True
        )

    def tearDown(self):
        cache.clear()

    def test_get_password_mode_shows_email_code_form(self):
        resp = self.client.get(LOGIN_URL + "?mode=password")

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'name="email"')
        self.assertContains(resp, "Send verification code")
        self.assertNotContains(resp, 'name="password"')
        self.assertNotContains(resp, 'name="mode"')

    @patch("apps.authn.views.admin.login.issue_email_challenge")
    def test_post_password_credentials_starts_email_code_flow(self, mock_issue):
        resp = self.client.post(
            LOGIN_URL, {"mode": "password", "email": "admin@example.com", "password": "testpass123"}
        )

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'name="code"')
        self.assertEqual(self.client.session.get("admin_login_step"), "code")
        mock_issue.assert_called_once()
        self.assertNotIn(LAST_ADMIN_LOGIN_COOKIE_NAME, resp.cookies)
        resp2 = self.client.get("/admin/")
        self.assertEqual(resp2.status_code, 302)

    def test_direct_password_post_does_not_log_in_with_pending_code(self):
        _create_pending_challenge(self.staff, "admin@example.com")
        session = self.client.session
        session["admin_login_step"] = "code"
        session["admin_login_email"] = "admin@example.com"
        session["admin_login_member_id"] = str(self.staff.pk)
        session.save()

        resp = self.client.post(
            LOGIN_URL, {"mode": "password", "email": "admin@example.com", "password": "testpass123"}
        )

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "This field is required")
        self.assertFalse(resp.wsgi_request.user.is_authenticated)

    @patch("apps.authn.views.admin.login.issue_email_challenge")
    def test_password_next_does_not_redirect_to_admin(self, _mock_issue):
        url = LOGIN_URL + "?next=/admin/cms/cmspage/"
        resp = self.client.post(url, {"mode": "password", "email": "admin@example.com", "password": "testpass123"})

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'name="code"')
        self.assertNotEqual(resp.status_code, 302)

    @patch("apps.authn.views.admin.login.issue_email_challenge")
    def test_password_mode_no_longer_clears_email_code_session(self, _mock_issue):
        self.client.post(LOGIN_URL, {"email": "admin@example.com"})
        self.assertEqual(self.client.session.get("admin_login_step"), "code")

        resp = self.client.get(LOGIN_URL + "?mode=password")

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'name="code"')
        self.assertNotContains(resp, 'name="password"')
        self.assertEqual(self.client.session.get("admin_login_step"), "code")

    def test_email_step_has_no_password_toggle(self):
        resp = self.client.get(LOGIN_URL)

        self.assertNotContains(resp, "Sign in with password instead")

    def test_remembered_admin_uses_email_code_only(self):
        self.client.cookies[LAST_ADMIN_LOGIN_COOKIE_NAME] = _last_admin_cookie_value(self.staff)

        resp = self.client.get(LOGIN_URL)

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Last signed in")
        self.assertContains(resp, "Send verification code")
        self.assertNotContains(resp, 'name="password"')
        self.assertNotContains(resp, 'name="email"')
