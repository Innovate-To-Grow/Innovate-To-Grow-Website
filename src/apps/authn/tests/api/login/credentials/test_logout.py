"""Tests for LogoutView — refresh-token blacklisting on user logout."""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APITestCase
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.authn.models import ContactEmail
from apps.authn.tests.helpers import (
    MALFORMED_REFRESH_BODIES,
    bearer_header,
    expired_bearer_header,
    stale_bearer_headers,
)

Member = get_user_model()
URL = "/authn/logout/"


class LogoutViewTests(APITestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.member = Member.objects.create_user(password="StrongPass123!", is_active=True)
        ContactEmail.objects.create(
            member=self.member, email_address="logout@example.com", email_type="primary", verified=True
        )

    def test_logout_blacklists_refresh_token(self):
        refresh = RefreshToken.for_user(self.member)
        response = self.client.post("/authn/logout/", {"refresh": str(refresh)}, format="json")
        self.assertEqual(response.status_code, 204)

        # Using the blacklisted refresh token must now fail.
        followup = self.client.post("/authn/refresh/", {"refresh": str(refresh)}, format="json")
        self.assertEqual(followup.status_code, 401)

    def test_logout_rejects_missing_refresh(self):
        response = self.client.post("/authn/logout/", {}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_logout_rejects_invalid_refresh(self):
        response = self.client.post("/authn/logout/", {"refresh": "not-a-real-token"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_logout_does_not_require_authentication(self):
        """An already-expired access token should not block logout."""
        refresh = RefreshToken.for_user(self.member)
        self.client.credentials()  # no Authorization header
        response = self.client.post("/authn/logout/", {"refresh": str(refresh)}, format="json")
        self.assertEqual(response.status_code, 204)

    def _is_blacklisted(self, refresh):
        return BlacklistedToken.objects.filter(token__jti=refresh["jti"]).exists()

    def test_expired_access_token_does_not_block_logout(self):
        """The SPA holds an expired access token when it logs out; the refresh token must still be revoked."""
        refresh = RefreshToken.for_user(self.member)

        response = self.client.post(
            URL, {"refresh": str(refresh)}, format="json", HTTP_AUTHORIZATION=expired_bearer_header(self.member)
        )

        self.assertEqual(response.status_code, 204)
        self.assertTrue(self._is_blacklisted(refresh))

    def test_stale_bearer_does_not_block_logout(self):
        for label, header in stale_bearer_headers().items():
            with self.subTest(bearer=label):
                refresh = RefreshToken.for_user(self.member)

                response = self.client.post(URL, {"refresh": str(refresh)}, format="json", HTTP_AUTHORIZATION=header)

                self.assertEqual(response.status_code, 204)
                self.assertTrue(self._is_blacklisted(refresh))

    def test_bearer_of_another_member_still_revokes_the_supplied_refresh_token(self):
        other = Member.objects.create_user(password="StrongPass123!", is_active=True)
        refresh = RefreshToken.for_user(self.member)

        response = self.client.post(
            URL, {"refresh": str(refresh)}, format="json", HTTP_AUTHORIZATION=bearer_header(other)
        )

        self.assertEqual(response.status_code, 204)
        self.assertTrue(self._is_blacklisted(refresh))

    def test_missing_blank_and_malformed_bodies_are_refresh_required_not_server_errors(self):
        """A JSON body may be ``null``, a list, a string or a number; only an object can carry the token."""
        bodies = {"empty object": "{}", "empty string": '{"refresh": ""}', "blank string": '{"refresh": "   "}'}
        for label, body in {**bodies, **MALFORMED_REFRESH_BODIES}.items():
            with self.subTest(body=label):
                response = self.client.post(URL, body, content_type="application/json")

                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.data, {"detail": "Refresh token is required."})

    def test_refresh_token_is_not_stripped_so_a_whitespace_wrapped_one_is_invalid_and_not_blacklisted(self):
        """The body is the credential and is used exactly as sent; ``/authn/refresh/`` trims it, logout must not."""
        for label, wrap in {
            "spaces both sides": " {} ",
            "leading tab": "\t{}",
            "trailing newline": "{}\n",
        }.items():
            with self.subTest(wrapped=label):
                refresh = RefreshToken.for_user(self.member)

                response = self.client.post(URL, {"refresh": wrap.format(refresh)}, format="json")

                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.data, {"detail": "Invalid or already-blacklisted token."})
                self.assertFalse(self._is_blacklisted(refresh))
                # Untouched: the exact token still logs out afterwards.
                self.assertEqual(self.client.post(URL, {"refresh": str(refresh)}, format="json").status_code, 204)
                self.assertTrue(self._is_blacklisted(refresh))

    def test_refresh_token_that_is_not_utf8_encodable_or_holds_nul_is_invalid_not_a_server_error(self):
        bodies = {
            "lone surrogate": '{"refresh": "\\ud800"}',
            "surrogate inside text": '{"refresh": "abc\\udfffdef"}',
            "NUL": '{"refresh": "a\\u0000b"}',
        }
        for label, body in bodies.items():
            with self.subTest(body=label):
                response = self.client.post(URL, body, content_type="application/json")

                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.data, {"detail": "Invalid or already-blacklisted token."})
