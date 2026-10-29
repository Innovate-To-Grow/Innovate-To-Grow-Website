"""Access tokens with certificate credentials (``private_key_jwt``) and the ``GraphCredential`` value object."""

from urllib.parse import parse_qs

import jwt
from cryptography import x509
from django.test import SimpleTestCase

from apps.core.services.email import PermanentEmailDeliveryError
from apps.core.services.email.graph import auth
from apps.core.services.email.graph.certificate import inspect_pair
from apps.core.tests.graph_helpers import certificate_pair
from apps.core.tests.services.test_email_graph import (
    ACCESS_TOKEN,
    CLIENT_ID,
    CLIENT_SECRET,
    TENANT_ID,
    GraphFixtureMixin,
    make_provider,
    simple_message,
    token_response,
)

AUDIENCE = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"


def _pair():
    certificate, key = certificate_pair()
    return certificate, key, inspect_pair(certificate, key).thumbprint


def certificate_credential(key, thumbprint, **overrides):
    values = {
        "tenant_id": TENANT_ID,
        "client_id": CLIENT_ID,
        "private_key_pem": key,
        "certificate_thumbprint": thumbprint,
    }
    return auth.GraphCredential(**{**values, **overrides})


def form(request):
    return {name: values[0] for name, values in parse_qs(request.body.decode()).items()}


class GraphCredentialTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.certificate, cls.key, cls.thumbprint = _pair()

    def test_repr_hides_the_secret_and_the_private_key(self):
        for credential in (
            auth.GraphCredential(tenant_id=TENANT_ID, client_id=CLIENT_ID, client_secret=CLIENT_SECRET),
            certificate_credential(self.key, self.thumbprint),
        ):
            with self.subTest(uses_certificate=credential.uses_certificate):
                text = repr(credential)
                self.assertNotIn(CLIENT_SECRET, text)
                self.assertNotIn("PRIVATE KEY", text)
                self.assertNotIn(self.key.splitlines()[1], text)
                self.assertIn(CLIENT_ID, text)

    def test_uses_certificate_follows_the_private_key(self):
        self.assertTrue(certificate_credential(self.key, self.thumbprint).uses_certificate)
        self.assertFalse(auth.GraphCredential(TENANT_ID, CLIENT_ID, client_secret=CLIENT_SECRET).uses_certificate)

    def test_cache_key_differs_per_key_and_per_thumbprint(self):
        _, other_key, other_thumbprint = _pair()
        base = certificate_credential(self.key, self.thumbprint).cache_key()

        self.assertNotEqual(base, certificate_credential(self.key, other_thumbprint).cache_key())
        self.assertNotEqual(base, certificate_credential(other_key + "\n", self.thumbprint).cache_key())
        self.assertNotEqual(base, auth.GraphCredential(TENANT_ID, CLIENT_ID, client_secret=CLIENT_SECRET).cache_key())
        self.assertEqual(base, certificate_credential(self.key, self.thumbprint).cache_key())

    def test_cache_key_never_contains_the_key_material(self):
        key = certificate_credential(self.key, self.thumbprint).cache_key()

        self.assertEqual(key[:2], (TENANT_ID, CLIENT_ID))
        self.assertEqual(len(key[2]), 64)
        self.assertNotIn("PRIVATE", "".join(key))

    def test_client_secret_fields(self):
        credential = auth.GraphCredential(TENANT_ID, CLIENT_ID, client_secret=CLIENT_SECRET)

        self.assertEqual(credential.authentication_fields(), {"client_secret": CLIENT_SECRET})

    def test_certificate_fields_carry_a_verifiable_assertion(self):
        fields = certificate_credential(self.key, self.thumbprint).authentication_fields()

        self.assertEqual(set(fields), {"client_assertion_type", "client_assertion"})
        self.assertEqual(fields["client_assertion_type"], "urn:ietf:params:oauth:client-assertion-type:jwt-bearer")
        public_key = x509.load_pem_x509_certificate(self.certificate.encode()).public_key()
        claims = jwt.decode(fields["client_assertion"], public_key, algorithms=["PS256"], audience=AUDIENCE)
        self.assertEqual(claims["sub"], CLIENT_ID)

    def test_unusable_key_is_permanent_and_never_echoes_key_material(self):
        # Assembled at runtime so secret scanners never see a PEM block in the source.
        marker = "PRIVATE" + " KEY"
        bad_key = f"-----BEGIN {marker}-----\nnot-real-key-material\n-----END {marker}-----"
        for label, key in {"unreadable": bad_key, "ec": certificate_pair(ec_key=True)[1]}.items():
            with self.subTest(label):
                with self.assertRaisesMessage(PermanentEmailDeliveryError, "private key could not be used") as caught:
                    certificate_credential(key, self.thumbprint).authentication_fields()
                self.assertNotIn("not-real-key-material", str(caught.exception))
                self.assertNotIn("PRIVATE KEY", str(caught.exception))


class CertificateTokenRequestTests(GraphFixtureMixin, SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.certificate, cls.key, cls.thumbprint = _pair()

    def test_token_request_sends_a_client_assertion_and_no_secret(self):
        token = auth.get_access_token(certificate_credential(self.key, self.thumbprint))

        self.assertEqual(token, ACCESS_TOKEN)
        (request,) = self.fake.token_requests
        self.assertEqual(request.path, f"/{TENANT_ID}/oauth2/v2.0/token")
        fields = form(request)
        self.assertNotIn("client_secret", fields)
        self.assertEqual(fields["client_assertion_type"], auth.CLIENT_ASSERTION_TYPE)
        self.assertEqual(fields["client_id"], CLIENT_ID)
        self.assertEqual(fields["grant_type"], "client_credentials")
        self.assertEqual(fields["scope"], "https://graph.microsoft.com/.default")
        header = jwt.get_unverified_header(fields["client_assertion"])
        self.assertEqual(header["x5t#S256"], self.thumbprint)
        self.assertNotIn(b"PRIVATE", request.body)

    def test_token_is_cached_per_certificate(self):
        credential = certificate_credential(self.key, self.thumbprint)
        auth.get_access_token(credential)
        auth.get_access_token(credential)
        self.assertEqual(len(self.fake.token_requests), 1)

        _, other_key, other_thumbprint = _pair()
        auth.get_access_token(certificate_credential(other_key + "\n", other_thumbprint))

        self.assertEqual(len(self.fake.token_requests), 2)

    def test_forget_drops_only_that_credential(self):
        credential = certificate_credential(self.key, self.thumbprint)
        auth.get_access_token(credential)

        auth.forget_access_token(credential)
        auth.get_access_token(credential)

        self.assertEqual(len(self.fake.token_requests), 2)

    def test_unusable_key_fails_before_any_request(self):
        credential = certificate_credential("not-a-key", self.thumbprint)

        with self.assertRaises(PermanentEmailDeliveryError):
            auth.get_access_token(credential)
        self.assertEqual(self.fake.requests, [])

    def test_provider_with_a_certificate_sends_through_the_assertion(self):
        provider = make_provider(client_secret="", private_key_pem=self.key, certificate_thumbprint=self.thumbprint)

        provider.send(simple_message())

        token_request, send_request = self.fake.requests
        self.assertIn("client_assertion", form(token_request))
        self.assertNotIn("client_secret", form(token_request))
        self.assertEqual(send_request.headers["Authorization"], f"Bearer {ACCESS_TOKEN}")
        self.assertNotIn(self.key, repr(provider))

    def test_provider_requires_the_thumbprint_with_a_private_key(self):
        with self.assertRaisesMessage(PermanentEmailDeliveryError, "configuration is invalid"):
            make_provider(client_secret="", private_key_pem=self.key, certificate_thumbprint="")

    def test_short_lived_token_is_cached_for_half_its_lifetime(self):
        self.script(token=token_response(expires_in=400))
        credential = certificate_credential(self.key, self.thumbprint)

        auth.get_access_token(credential)
        auth.get_access_token(credential)

        self.assertEqual(len(self.fake.token_requests), 1)
