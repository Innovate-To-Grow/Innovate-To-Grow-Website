"""
Tests for admin login via email verification code and password.
"""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.http import HttpResponse
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.authn.models import ContactEmail
from apps.authn.models.security import EmailAuthChallenge
from apps.authn.views.admin.login.state import LAST_ADMIN_LOGIN_COOKIE_NAME, set_last_admin_login_cookie

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


def _create_expired_challenge(member, email, code="123456"):
    return EmailAuthChallenge.objects.create(
        member=member,
        purpose=PURPOSE,
        target_email=email,
        code_hash=make_password(code),
        expires_at=timezone.now() - timedelta(minutes=1),
        max_attempts=5,
        status=EmailAuthChallenge.Status.EXPIRED,
        last_sent_at=timezone.now() - timedelta(minutes=11),
    )


def _last_admin_cookie_value(member):
    response = HttpResponse()
    set_last_admin_login_cookie(response, member)
    return response.cookies[LAST_ADMIN_LOGIN_COOKIE_NAME].value


class _AdminLoginViewCase(TestCase):
    # noinspection PyPep8Naming
    def setUp(self):
        self.staff = Member.objects.create_user(
            password="testpass123",
            is_staff=True,
            is_active=True,
        )
        ContactEmail.objects.create(
            member=self.staff, email_address="admin@example.com", email_type="primary", verified=True
        )
        self.non_staff = Member.objects.create_user(
            password="testpass123",
            is_staff=False,
            is_active=True,
        )
        ContactEmail.objects.create(
            member=self.non_staff, email_address="regular@example.com", email_type="primary", verified=True
        )


@override_settings(ROOT_URLCONF="config.routing.urls")
class AdminLoginViewTest(_AdminLoginViewCase):
    def test_get_shows_email_form(self):
        resp = self.client.get(LOGIN_URL)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'name="email"')
        self.assertContains(resp, "Send verification code")

    def test_get_without_last_admin_cookie_hides_last_signed_in_summary(self):
        resp = self.client.get(LOGIN_URL)
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "Last signed in")

    def test_get_with_last_admin_cookie_shows_member_summary(self):
        self.staff.first_name = "Ada"
        self.staff.last_name = "Lovelace"
        self.staff.organization = "Analytical Engines"
        self.staff.save(update_fields=["first_name", "last_name", "organization"])
        self.client.cookies[LAST_ADMIN_LOGIN_COOKIE_NAME] = _last_admin_cookie_value(self.staff)

        resp = self.client.get(LOGIN_URL)

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Last signed in")
        self.assertContains(resp, "Ada Lovelace")
        self.assertContains(resp, "Analytical Engines")
        self.assertContains(resp, 'name="password"')
        self.assertContains(resp, "Send verification code instead")
        self.assertNotContains(resp, "admin@example.com")
        self.assertNotContains(resp, 'name="email"')

    def test_get_with_tampered_last_admin_cookie_ignores_summary(self):
        self.client.cookies[LAST_ADMIN_LOGIN_COOKIE_NAME] = "tampered-cookie"

        resp = self.client.get(LOGIN_URL)

        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "Last signed in")

    def test_get_different_account_with_last_admin_cookie_shows_email_form(self):
        self.client.cookies[LAST_ADMIN_LOGIN_COOKIE_NAME] = _last_admin_cookie_value(self.staff)

        resp = self.client.get(LOGIN_URL + "?step=email&different=1")

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'name="email"')
        self.assertNotContains(resp, "Last signed in")
        self.assertNotContains(resp, "admin@example.com")

    def test_get_with_ineligible_last_admin_cookie_ignores_summary(self):
        inactive_staff = Member.objects.create_user(
            password="testpass123",
            first_name="Inactive",
            last_name="Admin",
            organization="Inactive Org",
            is_staff=True,
            is_active=False,
        )
        for member in (inactive_staff, self.non_staff):
            with self.subTest(member=member.pk):
                self.client.cookies[LAST_ADMIN_LOGIN_COOKIE_NAME] = _last_admin_cookie_value(member)

                resp = self.client.get(LOGIN_URL)

                self.assertEqual(resp.status_code, 200)
                self.assertNotContains(resp, "Last signed in")

    def test_authenticated_staff_redirects(self):
        self.client.force_login(self.staff)
        resp = self.client.get(LOGIN_URL)
        self.assertRedirects(resp, "/admin/", fetch_redirect_response=False)

    def test_authenticated_staff_post_redirects(self):
        """POST while already authenticated should redirect, not process the form."""
        self.client.force_login(self.staff)
        resp = self.client.post(LOGIN_URL, {"email": "admin@example.com"})
        self.assertRedirects(resp, "/admin/", fetch_redirect_response=False)

    def test_get_code_step_without_session_shows_email_form(self):
        """Directly visiting the code step without session state falls back to email form."""
        resp = self.client.get(LOGIN_URL)
        self.assertContains(resp, 'name="email"')
        self.assertNotContains(resp, 'name="code"')

    @patch("apps.authn.views.admin.login.issue_email_challenge")
    def test_post_valid_email_sends_code(self, mock_issue):
        resp = self.client.post(LOGIN_URL, {"email": "admin@example.com"})
        self.assertEqual(resp.status_code, 200)
        mock_issue.assert_called_once()
        call_kwargs = mock_issue.call_args.kwargs
        self.assertEqual(call_kwargs["member"], self.staff)
        self.assertEqual(call_kwargs["purpose"], PURPOSE)
        self.assertEqual(call_kwargs["target_email"], "admin@example.com")
        # Should show code form
        self.assertContains(resp, 'name="code"')
        self.assertContains(resp, "Verify and sign in")
        # Session should be on code step
        self.assertEqual(self.client.session.get("admin_login_step"), "code")
