from django.test import SimpleTestCase

from apps.cli_admin.pkce import verify_pkce_s256
from apps.cli_admin.redirect_uri import RedirectUriError, validate_loopback_redirect_uri


class PkceTests(SimpleTestCase):
    # RFC 7636 Appendix B reference vector.
    VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"

    def test_known_vector_matches(self):
        self.assertTrue(verify_pkce_s256(self.VERIFIER, self.CHALLENGE))

    def test_wrong_verifier_fails(self):
        self.assertFalse(verify_pkce_s256("not-the-verifier", self.CHALLENGE))

    def test_empty_verifier_fails(self):
        self.assertFalse(verify_pkce_s256("", self.CHALLENGE))

    def test_empty_challenge_fails(self):
        self.assertFalse(verify_pkce_s256(self.VERIFIER, ""))


class RedirectUriTests(SimpleTestCase):
    def test_valid_ipv4_loopback(self):
        uri = "http://127.0.0.1:54321/callback"
        self.assertEqual(validate_loopback_redirect_uri(uri), uri)

    def test_valid_ipv6_loopback(self):
        uri = "http://[::1]:54321/callback"
        self.assertEqual(validate_loopback_redirect_uri(uri), uri)

    def test_https_rejected(self):
        with self.assertRaises(RedirectUriError):
            validate_loopback_redirect_uri("https://127.0.0.1:54321/callback")

    def test_non_loopback_host_rejected(self):
        with self.assertRaises(RedirectUriError):
            validate_loopback_redirect_uri("http://evil.example.com:54321/callback")

    def test_localhost_name_rejected(self):
        with self.assertRaises(RedirectUriError):
            validate_loopback_redirect_uri("http://localhost:54321/callback")

    def test_embedded_credentials_rejected(self):
        with self.assertRaises(RedirectUriError):
            validate_loopback_redirect_uri("http://user:pass@127.0.0.1:54321/callback")

    def test_query_string_rejected(self):
        with self.assertRaises(RedirectUriError):
            validate_loopback_redirect_uri("http://127.0.0.1:54321/callback?x=1")

    def test_fragment_rejected(self):
        with self.assertRaises(RedirectUriError):
            validate_loopback_redirect_uri("http://127.0.0.1:54321/callback#frag")

    def test_wrong_path_rejected(self):
        with self.assertRaises(RedirectUriError):
            validate_loopback_redirect_uri("http://127.0.0.1:54321/evil")

    def test_invalid_port_rejected(self):
        with self.assertRaises(RedirectUriError):
            validate_loopback_redirect_uri("http://127.0.0.1:notaport/callback")

    def test_missing_port_rejected(self):
        with self.assertRaises(RedirectUriError):
            validate_loopback_redirect_uri("http://127.0.0.1/callback")
