"""Entra certificate credentials: certificate facts (thumbprints) and the signed client assertion (``private_key_jwt``)."""

import base64
import datetime
import hashlib
import time
import uuid
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from django.test import SimpleTestCase

from apps.core.services.email.graph.certificate import (
    build_client_assertion,
    describe_certificate,
    public_key_sha256,
)
from apps.core.tests.graph_helpers import make_certificate

TENANT_ID = "11111111-2222-3333-4444-555555555555"
CLIENT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
AUDIENCE = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"


def _other_rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


class DescribeCertificateTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.certificate, cls.key = make_certificate(days_valid=90)
        cls.facts = describe_certificate(cls.certificate)
        cls.der = cls.certificate.public_bytes(serialization.Encoding.DER)

    def test_sha1_thumbprint_is_the_upper_case_hex_entra_shows(self):
        self.assertEqual(self.facts.sha1_thumbprint, self.certificate.fingerprint(hashes.SHA1()).hex().upper())
        self.assertRegex(self.facts.sha1_thumbprint, r"^[0-9A-F]{40}$")

    def test_sha256_fingerprint_is_the_upper_case_hex_of_the_der(self):
        self.assertEqual(self.facts.sha256_fingerprint, hashlib.sha256(self.der).hexdigest().upper())

    def test_x5t_s256_is_unpadded_base64url_of_the_der_sha256(self):
        expected = base64.urlsafe_b64encode(hashlib.sha256(self.der).digest()).rstrip(b"=").decode()

        self.assertEqual(self.facts.x5t_s256, expected)
        self.assertEqual(len(self.facts.x5t_s256), 43)

    def test_public_key_hash_is_the_sha256_of_the_subject_public_key_info(self):
        spki = self.key.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )

        self.assertEqual(self.facts.public_key_sha256, hashlib.sha256(spki).hexdigest())
        self.assertEqual(public_key_sha256(self.key.public_key()), self.facts.public_key_sha256)

    def test_the_stored_certificate_is_the_re_serialised_leaf_only(self):
        self.assertEqual(self.facts.certificate_pem, self.certificate.public_bytes(serialization.Encoding.PEM).decode())
        self.assertNotIn("PRIVATE", self.facts.certificate_pem)

    def test_identity_and_validity_are_described(self):
        self.assertEqual((self.facts.subject, self.facts.issuer), ("CN=i2g-graph-test", "CN=i2g-graph-test"))
        self.assertEqual(self.facts.serial_number, format(self.certificate.serial_number, "X"))
        self.assertEqual(self.facts.key_bits, 2048)
        now = datetime.datetime.now(datetime.UTC)
        self.assertLess(self.facts.not_before, now)
        self.assertAlmostEqual(
            self.facts.not_after, now + datetime.timedelta(days=90), delta=datetime.timedelta(minutes=5)
        )


class BuildClientAssertionTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.certificate, cls.key = make_certificate()
        cls.thumbprint = describe_certificate(cls.certificate).x5t_s256
        cls.public_key = cls.certificate.public_key()

    def build(self, **overrides):
        values = {
            "tenant_id": TENANT_ID,
            "client_id": CLIENT_ID,
            "private_key": self.key,
            "x5t_s256": self.thumbprint,
        }
        return build_client_assertion(**{**values, **overrides})

    def decode(self, token, **options):
        return jwt.decode(token, self.public_key, algorithms=["PS256"], audience=AUDIENCE, **options)

    def test_signature_verifies_with_the_certificate_public_key(self):
        claims = self.decode(self.build())

        self.assertEqual(claims["aud"], AUDIENCE)
        self.assertEqual(claims["iss"], CLIENT_ID)
        self.assertEqual(claims["sub"], CLIENT_ID)

    def test_header_is_ps256_jwt_with_the_sha256_thumbprint(self):
        header = jwt.get_unverified_header(self.build())

        self.assertEqual(header["alg"], "PS256")
        self.assertEqual(header["typ"], "JWT")
        self.assertEqual(header["x5t#S256"], self.thumbprint)
        self.assertNotIn("x5t", header)

    def test_times_are_now_and_expire_after_five_minutes(self):
        with patch("apps.core.services.email.graph.certificate.time.time", return_value=1_800_000_000.7):
            token = self.build()

        claims = self.decode(token, options={"verify_exp": False, "verify_nbf": False, "verify_iat": False})
        self.assertEqual(claims["nbf"], 1_800_000_000)
        self.assertEqual(claims["iat"], 1_800_000_000)
        self.assertEqual(claims["exp"], 1_800_000_000 + settings.GRAPH_CLIENT_ASSERTION_LIFETIME_SECONDS)
        self.assertEqual(settings.GRAPH_CLIENT_ASSERTION_LIFETIME_SECONDS, 300)
        with self.settings(GRAPH_CLIENT_ASSERTION_LIFETIME_SECONDS=120):
            with patch("apps.core.services.email.graph.certificate.time.time", return_value=1_800_000_000):
                shorter = self.build()
        claims = self.decode(shorter, options={"verify_exp": False, "verify_nbf": False, "verify_iat": False})
        self.assertEqual(claims["exp"], 1_800_000_000 + 120)

    def test_current_assertion_is_valid_now(self):
        claims = self.decode(self.build())

        self.assertLessEqual(abs(claims["iat"] - int(time.time())), 5)

    def test_jti_is_a_fresh_uuid_for_each_assertion(self):
        first, second = self.decode(self.build())["jti"], self.decode(self.build())["jti"]

        self.assertNotEqual(first, second)
        self.assertEqual(str(uuid.UUID(first)), first)

    def test_audience_names_the_tenant_token_endpoint(self):
        token = self.build(tenant_id="contoso.onmicrosoft.com")

        claims = jwt.decode(
            token,
            self.public_key,
            algorithms=["PS256"],
            audience="https://login.microsoftonline.com/contoso.onmicrosoft.com/oauth2/v2.0/token",
        )
        self.assertEqual(claims["iss"], CLIENT_ID)

    def test_signature_fails_with_another_key(self):
        other_public = _other_rsa_key().public_key()

        with self.assertRaises(jwt.InvalidSignatureError):
            jwt.decode(self.build(), other_public, algorithms=["PS256"], audience=AUDIENCE)

    def test_rs256_is_not_accepted_for_the_assertion(self):
        with self.assertRaises(jwt.InvalidAlgorithmError):
            jwt.decode(self.build(), self.public_key, algorithms=["RS256"], audience=AUDIENCE)

    def test_the_assertion_never_contains_key_material(self):
        token = self.build()
        pem = self.key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        ).decode()

        for line in pem.splitlines()[1:-1]:
            self.assertNotIn(line, token)
