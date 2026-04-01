"""
Tests for admin login via email verification code and password.
"""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.test import TestCase, override_settings
from django.utils import timezone

from authn.models import ContactEmail
from authn.models.security import EmailAuthChallenge

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


@override_settings(ROOT_URLCONF="core.urls")
class AdminLoginViewTest(TestCase):
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

    def test_get_shows_email_form(self):
        resp = self.client.get(LOGIN_URL)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'name="email"')
        self.assertContains(resp, "Send verification code")

    def test_authenticated_staff_redirects(self):
        self.client.force_login(self.staff)
        resp = self.client.get(LOGIN_URL)
        self.assertRedirects(resp, "/admin/", fetch_redirect_response=False)

    @patch("authn.views.admin_login.issue_email_challenge")
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

    def test_post_non_staff_email_shows_error(self):
        resp = self.client.post(LOGIN_URL, {"email": "regular@example.com"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Unable to send verification code")
        # Should still show email form
        self.assertContains(resp, 'name="email"')
        # No challenge created
        self.assertEqual(EmailAuthChallenge.objects.filter(purpose=PURPOSE).count(), 0)

    def test_post_unknown_email_shows_error(self):
        resp = self.client.post(LOGIN_URL, {"email": "unknown@example.com"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Unable to send verification code")

    @patch("authn.views.admin_login.issue_email_challenge")
    # noinspection PyUnusedLocal
    def test_post_valid_code_logs_in(self, mock_issue):
        # Step 1: submit email
        self.client.post(LOGIN_URL, {"email": "admin@example.com"})

        # Create a pending challenge
        challenge = _create_pending_challenge(self.staff, "admin@example.com", code="654321")

        # Step 2: submit code
        with patch("authn.views.admin_login.verify_email_code", return_value=challenge):
            resp = self.client.post(LOGIN_URL, {"code": "654321"})

        self.assertRedirects(resp, "/admin/", fetch_redirect_response=False)
        # User should be authenticated
        resp2 = self.client.get("/admin/")
        self.assertEqual(resp2.status_code, 200)

    @patch("authn.views.admin_login.issue_email_challenge")
    # noinspection PyUnusedLocal
    def test_post_invalid_code_shows_error(self, mock_issue):
        # Step 1
        self.client.post(LOGIN_URL, {"email": "admin@example.com"})

        # Step 2 with invalid code
        from authn.services.email_challenges import AuthChallengeInvalid

        with patch("authn.views.admin_login.verify_email_code", side_effect=AuthChallengeInvalid("bad")):
            resp = self.client.post(LOGIN_URL, {"code": "000000"})

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Verification code is invalid or has expired")

    @patch("authn.views.admin_login.issue_email_challenge")
    def test_resend_action(self, mock_issue):
        # Step 1
        self.client.post(LOGIN_URL, {"email": "admin@example.com"})

        # Resend
        mock_issue.reset_mock()
        resp = self.client.post(LOGIN_URL, {"action": "resend"})
        self.assertEqual(resp.status_code, 200)
        mock_issue.assert_called_once()
        self.assertContains(resp, "A new verification code has been sent")

    @patch("authn.views.admin_login.issue_email_challenge")
    # noinspection PyUnusedLocal
    def test_step_email_query_resets_flow(self, mock_issue):
        # Step 1 → code step
        self.client.post(LOGIN_URL, {"email": "admin@example.com"})
        self.assertEqual(self.client.session.get("admin_login_step"), "code")

        # Reset via ?step=email
        resp = self.client.get(LOGIN_URL + "?step=email")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'name="email"')
        self.assertNotIn("admin_login_step", self.client.session)

    @patch("authn.views.admin_login.issue_email_challenge")
    # noinspection PyUnusedLocal
    def test_next_redirect_parameter(self, mock_issue):
        # Step 1
        url = LOGIN_URL + "?next=/admin/cms/cmspage/"
        self.client.post(url, {"email": "admin@example.com"})

        challenge = _create_pending_challenge(self.staff, "admin@example.com")

        with patch("authn.views.admin_login.verify_email_code", return_value=challenge):
            resp = self.client.post(url, {"code": "123456"})

        self.assertRedirects(resp, "/admin/cms/cmspage/", fetch_redirect_response=False)

    @patch("authn.views.admin_login.issue_email_challenge")
    # noinspection PyUnusedLocal
    def test_next_rejects_external_urls(self, mock_issue):
        url = LOGIN_URL + "?next=https://evil.com"
        self.client.post(url, {"email": "admin@example.com"})

        challenge = _create_pending_challenge(self.staff, "admin@example.com")

        with patch("authn.views.admin_login.verify_email_code", return_value=challenge):
            resp = self.client.post(url, {"code": "123456"})

        # Should redirect to /admin/ instead of external URL
        self.assertRedirects(resp, "/admin/", fetch_redirect_response=False)

    @patch("authn.views.admin_login.issue_email_challenge")
    def test_throttled_shows_error(self, mock_issue):
        from authn.services.email_challenges import AuthChallengeThrottled

        mock_issue.side_effect = AuthChallengeThrottled("Too many codes requested.")
        resp = self.client.post(LOGIN_URL, {"email": "admin@example.com"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Too many codes requested")
