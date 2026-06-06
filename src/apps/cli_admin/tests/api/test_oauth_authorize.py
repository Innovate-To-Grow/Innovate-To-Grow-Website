from unittest import mock
from urllib.parse import parse_qs, urlparse

from django.test import TestCase

from apps.cli_admin.models import CliAuthorizationCode
from apps.cli_admin.tests.helpers import VALID_REDIRECT_URI, challenge_for, make_member, make_staff

AUTHORIZE = "/admin-api/oauth/authorize/"


class OAuthAuthorizeTests(TestCase):
    def setUp(self):
        self.staff = make_staff(email="authz@example.com")
        self.verifier = "v" * 64
        self.challenge = challenge_for(self.verifier)

    def _params(self, **overrides):
        params = {
            "response_type": "code",
            "client_id": "i2g-admin-cli",
            "code_challenge": self.challenge,
            "code_challenge_method": "S256",
            "redirect_uri": VALID_REDIRECT_URI,
            "state": "client-state",
        }
        params.update(overrides)
        return {k: v for k, v in params.items() if v is not None}

    def _get_as_staff(self, **overrides):
        self.client.force_login(self.staff)
        return self.client.get(AUTHORIZE, self._params(**overrides))

    def test_unauthenticated_redirects_to_admin_login(self):
        response = self.client.get(AUTHORIZE, self._params())
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("/admin/login/?next="))

    def test_non_staff_redirects_to_admin_login(self):
        self.client.force_login(make_member(email="plain@example.com", is_staff=False))
        response = self.client.get(AUTHORIZE, self._params())
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("/admin/login/?next="))

    def test_unsafe_next_falls_back_to_authorize_path(self):
        # If get_full_path() ever yields a scheme/host-bearing value, the login
        # redirect must drop it and fall back to the bare authorize path so an
        # attacker can't smuggle an off-site ?next= target through this endpoint.
        with mock.patch(
            "django.http.request.HttpRequest.get_full_path",
            return_value="https://evil.example.com/phish",
        ):
            response = self.client.get(AUTHORIZE, self._params())
        self.assertEqual(response.status_code, 302)
        qs = parse_qs(urlparse(response["Location"]).query)
        self.assertEqual(qs["next"][0], AUTHORIZE)

    def test_valid_request_issues_hashed_code(self):
        response = self._get_as_staff()
        self.assertEqual(response.status_code, 302)
        location = response["Location"]
        self.assertTrue(location.startswith(VALID_REDIRECT_URI))
        qs = parse_qs(urlparse(location).query)
        self.assertEqual(qs["state"][0], "client-state")
        raw_code = qs["code"][0]
        row = CliAuthorizationCode.objects.get(code_hash=CliAuthorizationCode.hash_code(raw_code))
        self.assertEqual(row.member, self.staff)
        self.assertEqual(row.code_challenge, self.challenge)
        self.assertFalse(row.is_used)
        # The raw code is never stored verbatim.
        self.assertFalse(CliAuthorizationCode.objects.filter(code_hash=raw_code).exists())

    def test_bad_response_type_is_400(self):
        self.assertEqual(self._get_as_staff(response_type="token").status_code, 400)

    def test_unknown_client_id_is_400(self):
        self.assertEqual(self._get_as_staff(client_id="someone-else").status_code, 400)

    def test_non_s256_method_is_400(self):
        self.assertEqual(self._get_as_staff(code_challenge_method="plain").status_code, 400)

    def test_short_challenge_is_400(self):
        self.assertEqual(self._get_as_staff(code_challenge="tooshort").status_code, 400)

    def test_bad_redirect_uri_is_400(self):
        self.assertEqual(self._get_as_staff(redirect_uri="https://evil.example.com/callback").status_code, 400)

    def test_bad_redirect_uri_returns_public_message(self):
        # The 400 body is the validator's fixed public_message, not str(exc) or a
        # traceback — a helpful developer-facing hint with no exposed internals.
        response = self._get_as_staff(redirect_uri="https://127.0.0.1:54321/callback")
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"http scheme", response.content)
