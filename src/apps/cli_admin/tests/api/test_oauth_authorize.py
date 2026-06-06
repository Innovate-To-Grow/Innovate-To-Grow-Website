from unittest import mock
from urllib.parse import parse_qs, urlparse

from django.http import HttpResponseBadRequest, HttpResponseRedirect
from django.test import TestCase

from apps.cli_admin.models import CliAuthorizationCode
from apps.cli_admin.tests.helpers import VALID_REDIRECT_URI, challenge_for, make_member, make_staff
from apps.cli_admin.views.oauth import (
    ADMIN_LOGIN_PATH,
    _redirect_to_admin_login,
    _redirect_to_loopback_callback,
)

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
        qs = parse_qs(urlparse(response["Location"]).query)
        next_url = urlparse(qs["next"][0])
        self.assertEqual(next_url.path, AUTHORIZE)
        self.assertEqual(parse_qs(next_url.query)["client_id"][0], "i2g-admin-cli")

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

    def test_valid_ipv6_loopback_redirect_issues_code(self):
        response = self._get_as_staff(redirect_uri="http://[::1]:54321/callback")
        self.assertEqual(response.status_code, 302)
        location = response["Location"]
        self.assertTrue(location.startswith("http://[::1]:54321/callback?"))
        qs = parse_qs(urlparse(location).query)
        self.assertEqual(qs["state"][0], "client-state")

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

    def test_admin_login_redirect_falls_back_to_bare_path(self):
        # Defense-in-depth: ``_redirect_to_admin_login`` builds its login URL from
        # the constant ``ADMIN_LOGIN_PATH``, so the safety check on line 40 can
        # never fail through a normal request. Force the guard off to exercise the
        # fallback that drops the (potentially tampered) ?next= and redirects to
        # the bare admin-login path. Patching the symbol also flips
        # ``_safe_authorize_next_path``, so the path stays same-host regardless.
        request = self.client.get(AUTHORIZE, self._params()).wsgi_request
        with mock.patch(
            "apps.cli_admin.views.oauth.url_has_allowed_host_and_scheme",
            return_value=False,
        ):
            response = _redirect_to_admin_login(request)
        self.assertIsInstance(response, HttpResponseRedirect)
        self.assertEqual(response["Location"], ADMIN_LOGIN_PATH)

    def test_loopback_callback_rejects_unsafe_redirect_uri(self):
        # Defense-in-depth: in the normal flow ``redirect_uri`` is rebuilt by
        # ``validate_loopback_redirect_uri`` before reaching this helper, so the
        # 400 on line 52 is unreachable end-to-end. Call the helper directly with
        # a real unsafe value — a backslash in the authority makes
        # ``url_has_allowed_host_and_scheme`` reject the host even though it is in
        # the allowlist — to confirm it returns a 400 instead of redirecting.
        response = _redirect_to_loopback_callback(
            "http://127.0.0.1:7777\\@evil.example.com/callback",
            code="rawcode",
            state="client-state",
        )
        self.assertIsInstance(response, HttpResponseBadRequest)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b"redirect_uri is not allowed.")
