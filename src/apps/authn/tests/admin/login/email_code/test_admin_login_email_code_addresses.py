from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.hashers import make_password
from django.test import override_settings
from django.utils import timezone

from apps.authn.models import ContactEmail
from apps.authn.models.security import EmailAuthChallenge
from apps.authn.services.email.challenges import (
    AuthChallengeThrottled,
)
from apps.authn.tests.admin.login.email_code.test_admin_login_email_code import (
    LOGIN_URL,
    PURPOSE,
    Member,
    _AdminLoginViewCase,
    _create_pending_challenge,
)


@override_settings(ROOT_URLCONF="config.routing.urls")
class AdminLoginViewTest(_AdminLoginViewCase):
    @patch("apps.authn.views.admin.login.issue_email_challenge")
    def test_post_email_case_insensitive(self, mock_issue):
        """Email lookup should be case-insensitive."""
        resp = self.client.post(LOGIN_URL, {"email": "ADMIN@Example.COM"})
        self.assertEqual(resp.status_code, 200)
        mock_issue.assert_called_once()

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

    def test_post_empty_email_shows_error(self):
        """Empty email should fail form validation."""
        resp = self.client.post(LOGIN_URL, {"email": ""})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'name="email"')

    def test_post_invalid_email_format_shows_error(self):
        """Malformed email should fail form validation."""
        resp = self.client.post(LOGIN_URL, {"email": "not-an-email"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'name="email"')

    def test_unverified_email_shows_error(self):
        """Staff member with unverified email cannot receive a verification code."""
        unverified_staff = Member.objects.create_user(password="testpass123", is_staff=True, is_active=True)
        ContactEmail.objects.create(
            member=unverified_staff, email_address="unverified@example.com", email_type="primary", verified=False
        )
        resp = self.client.post(LOGIN_URL, {"email": "unverified@example.com"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Unable to send verification code")

    def test_inactive_staff_email_shows_error(self):
        """Inactive staff member should not be able to request a code."""
        inactive_staff = Member.objects.create_user(password="testpass123", is_staff=True, is_active=False)
        ContactEmail.objects.create(
            member=inactive_staff, email_address="inactive@example.com", email_type="primary", verified=True
        )
        resp = self.client.post(LOGIN_URL, {"email": "inactive@example.com"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Unable to send verification code")

    def test_staff_with_no_contact_email_shows_error(self):
        """Staff member without any ContactEmail cannot log in via email code."""
        Member.objects.create_user(password="testpass123", is_staff=True, is_active=True)
        # No ContactEmail created
        resp = self.client.post(LOGIN_URL, {"email": "nocontact@example.com"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Unable to send verification code")

    @patch("apps.authn.views.admin.login.issue_email_challenge")
    def test_throttled_shows_error(self, mock_issue):
        mock_issue.side_effect = AuthChallengeThrottled("Too many codes requested.")
        resp = self.client.post(LOGIN_URL, {"email": "admin@example.com"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Too many codes requested")

    @patch("apps.authn.views.admin.login.issue_email_challenge")
    def test_a_send_refused_by_the_address_limits_still_opens_the_code_step(self, mock_issue):
        """Anyone can request codes for a staff address; that must not keep the mailbox owner out.

        The refusal means a code went to the address a moment ago (here: requested by someone else). The owner is
        taken to the code step and signs in with the code they hold.
        """
        _create_pending_challenge(self.staff, "admin@example.com", code="246810")
        mock_issue.side_effect = AuthChallengeThrottled("Please wait before requesting another code.")

        resp = self.client.post(LOGIN_URL, {"email": "admin@example.com"})

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'name="code"')
        self.assertNotContains(resp, 'name="email"')
        self.assertContains(resp, "Please wait before requesting another code.")
        self.assertContains(resp, "enter the most recent one below")

        signed_in = self.client.post(LOGIN_URL, {"code": "246810"})

        self.assertEqual(signed_in.status_code, 302)
        self.assertEqual(self.client.get("/admin/").status_code, 200)

    @patch("apps.authn.views.admin.login.issue_email_challenge")
    def test_the_code_step_opened_by_a_refused_send_still_needs_the_code(self, mock_issue):
        _create_pending_challenge(self.staff, "admin@example.com", code="246810")
        mock_issue.side_effect = AuthChallengeThrottled("Please wait before requesting another code.")
        self.client.post(LOGIN_URL, {"email": "admin@example.com"})

        wrong = self.client.post(LOGIN_URL, {"code": "000000"})

        self.assertEqual(wrong.status_code, 200)
        self.assertContains(wrong, "Verification code is invalid or has expired.")
        self.assertEqual(self.client.get("/admin/").status_code, 302)

    @patch("apps.authn.views.admin.login.issue_email_challenge")
    def test_a_refused_send_without_a_usable_admin_code_stays_on_the_email_step(self, mock_issue):
        """The address limits are shared by every code endpoint: a refusal alone does not mean an admin code exists."""
        mock_issue.side_effect = AuthChallengeThrottled("Please wait before requesting another code.")

        resp = self.client.post(LOGIN_URL, {"email": "admin@example.com"})

        self.assertContains(resp, 'name="email"')
        self.assertNotContains(resp, 'name="code"')
        self.assertContains(resp, "Please wait before requesting another code.")
        self.assertNotContains(resp, "enter the most recent one below")

    @patch("apps.authn.views.admin.login.issue_email_challenge")
    def test_a_sign_in_code_of_another_kind_does_not_open_the_admin_code_step(self, mock_issue):
        EmailAuthChallenge.objects.create(
            member=self.staff,
            purpose=EmailAuthChallenge.Purpose.LOGIN,
            target_email="admin@example.com",
            code_hash=make_password("135790"),
            expires_at=timezone.now() + timedelta(minutes=10),
            max_attempts=5,
            last_sent_at=timezone.now(),
        )
        mock_issue.side_effect = AuthChallengeThrottled("Please wait before requesting another code.")

        resp = self.client.post(LOGIN_URL, {"email": "admin@example.com"})

        self.assertContains(resp, 'name="email"')
        self.assertNotContains(resp, 'name="code"')

    @patch("apps.authn.views.admin.login.issue_email_challenge")
    def test_a_spent_or_expired_admin_code_does_not_open_the_code_step(self, mock_issue):
        mock_issue.side_effect = AuthChallengeThrottled("Please wait before requesting another code.")
        spent = _create_pending_challenge(self.staff, "admin@example.com")
        spent.attempts = spent.max_attempts
        spent.save(update_fields=["attempts"])

        resp = self.client.post(LOGIN_URL, {"email": "admin@example.com"})
        self.assertNotContains(resp, 'name="code"')

        EmailAuthChallenge.objects.all().delete()
        timed_out = _create_pending_challenge(self.staff, "admin@example.com")
        timed_out.expires_at = timezone.now() - timedelta(seconds=1)
        timed_out.save(update_fields=["expires_at"])

        resp = self.client.post(LOGIN_URL, {"email": "admin@example.com"})
        self.assertNotContains(resp, 'name="code"')
