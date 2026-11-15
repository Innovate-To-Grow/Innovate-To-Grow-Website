from unittest.mock import patch

from django.test import override_settings

from apps.authn.services.email.challenges import (
    AuthChallengeDeliveryError,
    AuthChallengeThrottled,
)
from apps.authn.tests.admin.login.email_code.test_admin_login_email_code import (
    LOGIN_URL,
    PURPOSE,
    _AdminLoginViewCase,
    _create_pending_challenge,
    _last_admin_cookie_value,
)
from apps.authn.views.admin.login.state import LAST_ADMIN_LOGIN_COOKIE_NAME


@override_settings(ROOT_URLCONF="config.routing.urls")
class AdminLoginViewTest(_AdminLoginViewCase):
    @patch("apps.authn.views.admin.login.issue_email_challenge")
    # noinspection PyUnusedLocal
    def test_member_deactivated_between_steps_shows_error(self, mock_issue):
        """If member becomes inactive between email and code step, access is denied."""
        self.client.post(LOGIN_URL, {"email": "admin@example.com"})

        challenge = _create_pending_challenge(self.staff, "admin@example.com", code="654321")

        self.staff.is_active = False
        self.staff.save()

        with patch("apps.authn.views.admin.login.verify_email_code", return_value=challenge):
            resp = self.client.post(LOGIN_URL, {"code": "654321"})

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "You do not have access to the admin panel")

    @patch("apps.authn.views.admin.login.issue_email_challenge")
    # noinspection PyUnusedLocal
    def test_code_step_hides_last_admin_summary(self, mock_issue):
        self.client.cookies[LAST_ADMIN_LOGIN_COOKIE_NAME] = _last_admin_cookie_value(self.staff)

        resp = self.client.post(LOGIN_URL, {"email": "admin@example.com"})

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'name="code"')
        self.assertNotContains(resp, "Last signed in")

    @patch("apps.authn.views.admin.login.issue_email_challenge")
    def test_remembered_admin_can_request_code_without_email_display(self, mock_issue):
        self.staff.first_name = "Ada"
        self.staff.last_name = "Lovelace"
        self.staff.save(update_fields=["first_name", "last_name"])
        self.client.cookies[LAST_ADMIN_LOGIN_COOKIE_NAME] = _last_admin_cookie_value(self.staff)

        resp = self.client.post(LOGIN_URL, {"action": "remembered_code"})

        self.assertEqual(resp.status_code, 200)
        mock_issue.assert_called_once()
        call_kwargs = mock_issue.call_args.kwargs
        self.assertEqual(call_kwargs["member"], self.staff)
        self.assertEqual(call_kwargs["purpose"], PURPOSE)
        self.assertEqual(call_kwargs["target_email"], "admin@example.com")
        self.assertContains(resp, 'name="code"')
        self.assertContains(resp, "A verification code has been sent to Ada Lovelace.")
        self.assertContains(resp, "We sent a 6-digit code to Ada Lovelace.")
        self.assertNotContains(resp, "admin@example.com")
        self.assertEqual(self.client.session.get("admin_login_step"), "code")
        self.assertTrue(self.client.session.get("admin_login_hide_email"))

    @patch("apps.authn.views.admin.login.issue_email_challenge")
    def test_resend_action(self, mock_issue):
        # Step 1
        self.client.post(LOGIN_URL, {"email": "admin@example.com"})

        # Resend
        mock_issue.reset_mock()
        resp = self.client.post(LOGIN_URL, {"action": "resend"})
        self.assertEqual(resp.status_code, 200)
        mock_issue.assert_called_once()
        self.assertContains(resp, "A new verification code has been sent")

    @patch("apps.authn.views.admin.login.issue_email_challenge")
    def test_resend_delivery_failure_shows_message(self, mock_issue):
        # Step 1: submit email successfully
        self.client.post(LOGIN_URL, {"email": "admin@example.com"})

        # Resend fails
        mock_issue.reset_mock()
        mock_issue.side_effect = AuthChallengeDeliveryError("Failed to send verification email.", outcome="permanent")
        resp = self.client.post(LOGIN_URL, {"action": "resend"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Failed to send verification code")

    @patch("apps.authn.views.admin.login.issue_email_challenge")
    def test_resend_throttled_shows_message(self, mock_issue):
        """Resend that hits rate limit shows the throttle message, not an error page."""
        self.client.post(LOGIN_URL, {"email": "admin@example.com"})

        mock_issue.reset_mock()
        mock_issue.side_effect = AuthChallengeThrottled("Please wait before requesting another code.")
        resp = self.client.post(LOGIN_URL, {"action": "resend"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Please wait before requesting another code")
        # Should still show code form
        self.assertContains(resp, 'name="code"')

    @patch("apps.authn.views.admin.login.issue_email_challenge")
    def test_resend_with_deleted_member_resets_to_email(self, mock_issue):
        """If the member is deleted between steps, resend should reset to email form."""
        self.client.post(LOGIN_URL, {"email": "admin@example.com"})

        # Delete the member
        self.staff.delete()

        mock_issue.reset_mock()
        resp = self.client.post(LOGIN_URL, {"action": "resend"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'name="email"')
        mock_issue.assert_not_called()

    @patch("apps.authn.views.admin.login.issue_email_challenge")
    def test_resend_with_demoted_member_resets_to_email(self, mock_issue):
        """If the member loses staff status, resend should reset to email form."""
        self.client.post(LOGIN_URL, {"email": "admin@example.com"})

        self.staff.is_staff = False
        self.staff.save()

        mock_issue.reset_mock()
        resp = self.client.post(LOGIN_URL, {"action": "resend"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'name="email"')
        mock_issue.assert_not_called()

    @patch("apps.authn.views.admin.login.issue_email_challenge")
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

    @patch("apps.authn.views.admin.login.issue_email_challenge")
    # noinspection PyUnusedLocal
    def test_next_redirect_parameter(self, mock_issue):
        # Step 1
        url = LOGIN_URL + "?next=/admin/cms/cmspage/"
        self.client.post(url, {"email": "admin@example.com"})

        challenge = _create_pending_challenge(self.staff, "admin@example.com")

        with patch("apps.authn.views.admin.login.verify_email_code", return_value=challenge):
            resp = self.client.post(url, {"code": "123456"})

        self.assertRedirects(resp, "/admin/cms/cmspage/", fetch_redirect_response=False)

    @patch("apps.authn.views.admin.login.issue_email_challenge")
    # noinspection PyUnusedLocal
    def test_next_rejects_external_urls(self, mock_issue):
        url = LOGIN_URL + "?next=https://evil.com"
        self.client.post(url, {"email": "admin@example.com"})

        challenge = _create_pending_challenge(self.staff, "admin@example.com")

        with patch("apps.authn.views.admin.login.verify_email_code", return_value=challenge):
            resp = self.client.post(url, {"code": "123456"})

        # Should redirect to /admin/ instead of external URL
        self.assertRedirects(resp, "/admin/", fetch_redirect_response=False)
