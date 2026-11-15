from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.hashers import make_password
from django.utils import timezone

from apps.authn.models.security import EmailAuthChallenge
from apps.authn.tests.admin.login.password.lockout.test_admin_login_lockout import (
    ALICE,
    LOCKED,
    LOGIN_URL,
    PASSWORD,
    AdminLockoutTestCase,
)


class EmailCodeLoginWhileLockedTests(AdminLockoutTestCase):
    """The lockout is on passwords only: a locked admin can still sign in with an email code."""

    def _pending_challenge(self, member, email):
        return EmailAuthChallenge.objects.create(
            member=member,
            purpose=EmailAuthChallenge.Purpose.ADMIN_LOGIN,
            target_email=email,
            code_hash=make_password("654321"),
            expires_at=timezone.now() + timedelta(minutes=10),
            max_attempts=5,
            last_sent_at=timezone.now(),
        )

    def test_the_typed_email_code_flow_signs_in_a_locked_admin(self):
        self.lock_password_form(ALICE)
        client = self.browser()

        with patch("apps.authn.views.admin.login.issue_email_challenge") as issue:
            response = client.post(LOGIN_URL, {"email": ALICE})
        issue.assert_called_once()
        self.assertContains(response, 'name="code"')

        challenge = self._pending_challenge(self.alice, ALICE)
        with patch("apps.authn.views.admin.login.verify_email_code", return_value=challenge):
            response = client.post(LOGIN_URL, {"code": "654321"})

        self.assertSignedIn(client, response)
        # Signing in by code proves nothing about the password, so the password lock stays until its window ends.
        self.assertEqual(self.errors(self.password_login(self.browser(), ALICE, PASSWORD)), [LOCKED])

    def test_the_remembered_email_code_flow_signs_in_a_locked_admin(self):
        client = self.lock_remembered_form(self.alice)

        with patch("apps.authn.views.admin.login.issue_email_challenge") as issue:
            response = client.post(LOGIN_URL, {"action": "remembered_code"})
        issue.assert_called_once()
        self.assertContains(response, 'name="code"')

        challenge = self._pending_challenge(self.alice, ALICE)
        with patch("apps.authn.views.admin.login.verify_email_code", return_value=challenge):
            response = client.post(LOGIN_URL, {"code": "654321"})

        self.assertSignedIn(client, response)

    def test_the_locked_page_still_offers_the_email_code_login(self):
        client = self.lock_remembered_form(self.alice)

        response = self.remembered_login(client, PASSWORD)

        self.assertContains(response, LOCKED)
        self.assertContains(response, "Send verification code instead")
