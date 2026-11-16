from datetime import timedelta

from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken

from apps.cli_admin.tests.helpers import CliApiTestCase, issue_token, make_staff

WHOAMI = "/admin-api/whoami/"


class AuthenticationTests(CliApiTestCase):
    def setUp(self):
        super().setUp()
        self.staff = make_staff(email="auth@example.com")

    def test_no_token_is_401(self):
        self.assertEqual(self.client.get(WHOAMI).status_code, 401)

    def test_non_bearer_scheme_is_401(self):
        self.assertEqual(self.client.get(WHOAMI, HTTP_AUTHORIZATION="Basic abc").status_code, 401)

    def test_bearer_without_credentials_is_401(self):
        self.assertEqual(self.client.get(WHOAMI, HTTP_AUTHORIZATION="Bearer").status_code, 401)

    def test_bearer_with_spaces_is_401(self):
        self.assertEqual(self.client.get(WHOAMI, HTTP_AUTHORIZATION="Bearer a b").status_code, 401)

    def test_unknown_token_is_401(self):
        self.assertEqual(self.client.get(WHOAMI, **self.auth("nonsense")).status_code, 401)

    def test_expired_token_is_401(self):
        _, raw = issue_token(self.staff, expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.get(WHOAMI, **self.auth(raw)).status_code, 401)

    def test_revoked_token_is_401(self):
        _, raw = issue_token(self.staff, revoked_at=timezone.now())
        self.assertEqual(self.client.get(WHOAMI, **self.auth(raw)).status_code, 401)

    def test_inactive_member_token_is_401(self):
        token, raw = issue_token(self.staff)
        self.staff.is_active = False
        self.staff.save(update_fields=["is_active"])
        self.assertEqual(self.client.get(WHOAMI, **self.auth(raw)).status_code, 401)

    def test_non_staff_member_token_is_401(self):
        _, raw = issue_token(self.staff)
        self.staff.is_staff = False
        self.staff.save(update_fields=["is_staff"])
        self.assertEqual(self.client.get(WHOAMI, **self.auth(raw)).status_code, 401)

    def test_simplejwt_token_is_rejected(self):
        jwt = str(AccessToken.for_user(self.staff))
        self.assertEqual(self.client.get(WHOAMI, **self.auth(jwt)).status_code, 401)

    def test_valid_token_authenticates_and_touches_last_used(self):
        token, raw = issue_token(self.staff)
        self.assertIsNone(token.last_used_at)
        response = self.client.get(WHOAMI, **self.auth(raw))
        self.assertEqual(response.status_code, 200)
        token.refresh_from_db()
        self.assertIsNotNone(token.last_used_at)
