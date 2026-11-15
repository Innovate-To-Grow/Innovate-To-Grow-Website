from unittest.mock import patch

from django.test import override_settings

from apps.authn.services.email.challenges import (
    AuthChallengeDeliveryError,
    AuthChallengeInvalid,
    AuthChallengeThrottled,
)
from apps.authn.tests.admin.login.email_code.test_admin_login_email_code import (
    LOGIN_URL,
    _AdminLoginViewCase,
    _create_pending_challenge,
)
from apps.authn.views.admin.login.state import LAST_ADMIN_LOGIN_COOKIE_NAME


@override_settings(ROOT_URLCONF="config.routing.urls")
class AdminLoginViewTest(_AdminLoginViewCase):
    def test_a_send_refused_for_any_other_reason_stays_on_the_email_step(self):
        """Only a 429 from the address limits can open the code step; a missing proof or a conflict cannot."""
        from rest_framework.response import Response

        _create_pending_challenge(self.staff, "admin@example.com", code="246810")
        for status_code, body in (
            (400, {"detail": "Verification is required before a code can be sent.", "code": "verification_required"}),
            (409, {"detail": "This request conflicts with an earlier one.", "code": "request_conflict"}),
            (503, {"detail": "Sending is unavailable."}),
        ):
            with self.subTest(status_code=status_code):
                with patch(
                    "apps.authn.views.admin.login.code_sending.guarded_send",
                    return_value=Response(body, status=status_code),
                ):
                    resp = self.client.post(LOGIN_URL, {"email": "admin@example.com"})

                self.assertContains(resp, 'name="email"')
                self.assertNotContains(resp, 'name="code"')
                self.assertNotContains(resp, "enter the most recent one below")

    @patch("apps.authn.views.admin.login.issue_email_challenge")
    def test_a_refused_send_for_a_non_staff_address_never_reaches_the_code_step(self, mock_issue):
        mock_issue.side_effect = AuthChallengeThrottled("Please wait before requesting another code.")

        resp = self.client.post(LOGIN_URL, {"email": "regular@example.com"})

        self.assertNotContains(resp, 'name="code"')
        mock_issue.assert_not_called()

    @patch("apps.authn.views.admin.login.issue_email_challenge")
    def test_delivery_failure_shows_error(self, mock_issue):
        mock_issue.side_effect = AuthChallengeDeliveryError("Failed to send verification email.", outcome="permanent")
        resp = self.client.post(LOGIN_URL, {"email": "admin@example.com"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Failed to send verification code")
        # Should stay on email form so user can retry
        self.assertContains(resp, 'name="email"')

    @patch("apps.authn.views.admin.login.issue_email_challenge")
    def test_delivery_failure_does_not_advance_to_code_step(self, mock_issue):
        """When email delivery fails, session should NOT move to 'code' step."""
        mock_issue.side_effect = AuthChallengeDeliveryError("boom", outcome="permanent")
        self.client.post(LOGIN_URL, {"email": "admin@example.com"})
        self.assertNotEqual(self.client.session.get("admin_login_step"), "code")

    @patch("apps.authn.views.admin.login.issue_email_challenge")
    # noinspection PyUnusedLocal
    def test_post_valid_code_logs_in(self, mock_issue):
        # Step 1: submit email
        self.client.post(LOGIN_URL, {"email": "admin@example.com"})

        # Create a pending challenge
        challenge = _create_pending_challenge(self.staff, "admin@example.com", code="654321")

        # Step 2: submit code
        with patch("apps.authn.views.admin.login.verify_email_code", return_value=challenge):
            resp = self.client.post(LOGIN_URL, {"code": "654321"})

        self.assertRedirects(resp, "/admin/", fetch_redirect_response=False)
        # User should be authenticated
        resp2 = self.client.get("/admin/")
        self.assertEqual(resp2.status_code, 200)

    @patch("apps.authn.views.admin.login.issue_email_challenge")
    # noinspection PyUnusedLocal
    def test_post_valid_code_sets_last_admin_cookie(self, mock_issue):
        self.client.post(LOGIN_URL, {"email": "admin@example.com"})
        challenge = _create_pending_challenge(self.staff, "admin@example.com", code="654321")

        with patch("apps.authn.views.admin.login.verify_email_code", return_value=challenge):
            resp = self.client.post(LOGIN_URL, {"code": "654321"})

        self.assertIn(LAST_ADMIN_LOGIN_COOKIE_NAME, resp.cookies)
        cookie = resp.cookies[LAST_ADMIN_LOGIN_COOKIE_NAME]
        self.assertEqual(cookie["path"], "/admin/")
        self.assertTrue(cookie["httponly"])

    @patch("apps.authn.views.admin.login.issue_email_challenge")
    # noinspection PyUnusedLocal
    def test_post_valid_code_clears_session(self, mock_issue):
        """Session login state should be cleaned up after successful code verification."""
        self.client.post(LOGIN_URL, {"email": "admin@example.com"})
        self.assertEqual(self.client.session.get("admin_login_step"), "code")

        challenge = _create_pending_challenge(self.staff, "admin@example.com", code="654321")
        with patch("apps.authn.views.admin.login.verify_email_code", return_value=challenge):
            self.client.post(LOGIN_URL, {"code": "654321"})

        self.assertNotIn("admin_login_step", self.client.session)
        self.assertNotIn("admin_login_email", self.client.session)
        self.assertNotIn("admin_login_member_id", self.client.session)

    @patch("apps.authn.views.admin.login.issue_email_challenge")
    # noinspection PyUnusedLocal
    def test_post_invalid_code_shows_error(self, mock_issue):
        # Step 1
        self.client.post(LOGIN_URL, {"email": "admin@example.com"})

        # Step 2 with invalid code
        with patch("apps.authn.views.admin.login.verify_email_code", side_effect=AuthChallengeInvalid("bad")):
            resp = self.client.post(LOGIN_URL, {"code": "000000"})

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Verification code is invalid or has expired", count=1)

    @patch("apps.authn.views.admin.login.issue_email_challenge")
    # noinspection PyUnusedLocal
    def test_invalid_code_stays_on_code_step(self, mock_issue):
        """After entering a wrong code the user should still be on the code step, not kicked to email."""
        self.client.post(LOGIN_URL, {"email": "admin@example.com"})

        with patch("apps.authn.views.admin.login.verify_email_code", side_effect=AuthChallengeInvalid("bad")):
            resp = self.client.post(LOGIN_URL, {"code": "000000"})

        self.assertContains(resp, 'name="code"')
        self.assertEqual(self.client.session.get("admin_login_step"), "code")

    @patch("apps.authn.views.admin.login.issue_email_challenge")
    # noinspection PyUnusedLocal
    def test_short_code_fails_validation(self, mock_issue):
        """Code shorter than 6 digits should fail form validation."""
        self.client.post(LOGIN_URL, {"email": "admin@example.com"})
        resp = self.client.post(LOGIN_URL, {"code": "123"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'name="code"')

    @patch("apps.authn.views.admin.login.issue_email_challenge")
    # noinspection PyUnusedLocal
    def test_code_step_without_session_redirects_to_email(self, mock_issue):
        """Submitting a code without prior email step should reset to email form."""
        # Directly POST a code without going through email step first
        resp = self.client.post(LOGIN_URL, {"code": "123456"})
        self.assertEqual(resp.status_code, 200)
        # Should show email form since no session state
        self.assertContains(resp, 'name="email"')

    @patch("apps.authn.views.admin.login.issue_email_challenge")
    # noinspection PyUnusedLocal
    def test_staff_deactivated_between_steps_shows_error(self, mock_issue):
        """If member loses staff status between email and code step, access is denied."""
        self.client.post(LOGIN_URL, {"email": "admin@example.com"})

        challenge = _create_pending_challenge(self.staff, "admin@example.com", code="654321")

        # Deactivate staff between steps
        self.staff.is_staff = False
        self.staff.save()

        with patch("apps.authn.views.admin.login.verify_email_code", return_value=challenge):
            resp = self.client.post(LOGIN_URL, {"code": "654321"})

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "You do not have access to the admin panel")
