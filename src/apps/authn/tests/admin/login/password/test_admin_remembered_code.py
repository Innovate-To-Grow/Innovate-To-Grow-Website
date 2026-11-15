from unittest.mock import patch

from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.authn.models import ContactEmail
from apps.authn.models.security import EmailAuthChallenge
from apps.authn.services.email.challenges import AuthChallengeDeliveryError, AuthChallengeThrottled
from apps.authn.tests.admin.login.password.test_admin_login_edge_cases import (
    LOGIN_URL,
    PURPOSE,
    Member,
    _signed_cookie_value,
)
from apps.authn.views.admin.login.state import (
    LAST_ADMIN_LOGIN_COOKIE_NAME,
)


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
