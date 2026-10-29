"""Entra certificate credentials: PEM pair inspection and the signed client assertion (``private_key_jwt``)."""

import base64
import datetime
import hashlib
import time
import uuid
from unittest.mock import patch

import jwt
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.test import SimpleTestCase

from apps.core.services.email.graph.certificate import (
    ASSERTION_LIFETIME_SECONDS,
    CertificateError,
    CertificateInfo,
    build_client_assertion,
    inspect_pair,
    load_private_key,
)
from apps.core.tests.graph_helpers import certificate_pair

TENANT_ID = "11111111-2222-3333-4444-555555555555"
CLIENT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
AUDIENCE = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"


def _expected_thumbprint(certificate_pem):
    der = x509.load_pem_x509_certificate(certificate_pem.encode()).public_bytes(serialization.Encoding.DER)
    return base64.urlsafe_b64encode(hashlib.sha256(der).digest()).rstrip(b"=").decode()


def _encrypted(key_pem):
    key = serialization.load_pem_private_key(key_pem.encode(), password=None)
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(b"not-a-real-passphrase"),
    ).decode()


def _other_rsa_key_pem():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()


class InspectPairTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.certificate, cls.key = certificate_pair(days_valid=90)

    def test_a_matching_rsa_pair_is_described(self):
        info = inspect_pair(self.certificate, self.key)

        self.assertIsInstance(info, CertificateInfo)
        self.assertEqual(info.thumbprint, _expected_thumbprint(self.certificate))
        self.assertEqual(info.subject, "CN=i2g-graph-test")
        now = datetime.datetime.now(datetime.UTC)
        self.assertLess(info.not_before, now)
        self.assertAlmostEqual(info.not_after, now + datetime.timedelta(days=90), delta=datetime.timedelta(minutes=5))

    def test_thumbprint_is_unpadded_base64url_of_the_der_sha256(self):
        thumbprint = inspect_pair(self.certificate, self.key).thumbprint

        self.assertEqual(len(thumbprint), 43)
        self.assertNotIn("=", thumbprint)
        self.assertNotIn("+", thumbprint)
        self.assertNotIn("/", thumbprint)

    def test_surrounding_whitespace_is_tolerated(self):
        info = inspect_pair(f"\n  {self.certificate}\n", f"  {self.key}\n\n")

        self.assertEqual(info.thumbprint, _expected_thumbprint(self.certificate))

    def test_an_expired_certificate_is_still_described(self):
        certificate, key = certificate_pair(days_valid=-1, not_before_days=-30)

        info = inspect_pair(certificate, key)

        self.assertLess(info.not_after, datetime.datetime.now(datetime.UTC))

    def test_a_key_from_another_certificate_is_refused(self):
        with self.assertRaisesMessage(CertificateError, "does not belong to this certificate"):
            inspect_pair(self.certificate, _other_rsa_key_pem())

    def test_an_ec_certificate_is_refused(self):
        certificate, key = certificate_pair(ec_key=True)

        with self.assertRaisesMessage(CertificateError, "must use an RSA key"):
            inspect_pair(certificate, key)

    def test_a_1024_bit_key_is_refused(self):
        certificate, key = certificate_pair(key_size=1024)

        with self.assertRaisesMessage(CertificateError, "at least 2048 bits"):
            inspect_pair(certificate, key)

    def test_an_encrypted_key_is_refused_without_echoing_it(self):
        encrypted = _encrypted(self.key)

        with self.assertRaisesMessage(CertificateError, "must not be password-protected") as caught:
            inspect_pair(self.certificate, encrypted)
        self.assertNotIn("PRIVATE KEY", str(caught.exception))

    def test_unreadable_certificates_are_refused(self):
        for label, value in {"garbage": "not a certificate", "blank": "", "none": None, "non-ascii": "caf\xe9"}.items():
            with self.subTest(label):
                with self.assertRaisesMessage(CertificateError, "not a readable PEM certificate"):
                    inspect_pair(value, self.key)

    def test_unreadable_keys_are_refused_without_echoing_them(self):
        for label, value in {"garbage": "secret-garbage-value", "blank": "", "non-ascii": "cl\xe9"}.items():
            with self.subTest(label):
                with self.assertRaisesMessage(CertificateError, "not a readable PEM private key") as caught:
                    inspect_pair(self.certificate, value)
                self.assertNotIn("secret-garbage-value", str(caught.exception))

    def test_a_certificate_passed_as_the_key_is_refused(self):
        with self.assertRaises(CertificateError):
            inspect_pair(self.certificate, self.certificate)

    def test_certificate_error_is_a_value_error(self):
        self.assertTrue(issubclass(CertificateError, ValueError))


class LoadPrivateKeyTests(SimpleTestCase):
    def test_returns_the_rsa_key(self):
        _, key = certificate_pair()

        self.assertIsInstance(load_private_key(key), rsa.RSAPrivateKey)

    def test_an_ec_key_is_refused(self):
        _, key = certificate_pair(ec_key=True)

        with self.assertRaisesMessage(CertificateError, "must use an RSA key"):
            load_private_key(key)

    def test_none_is_unreadable(self):
        with self.assertRaisesMessage(CertificateError, "not a readable PEM private key"):
            load_private_key(None)


class BuildClientAssertionTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.certificate, cls.key = certificate_pair()
        cls.thumbprint = inspect_pair(cls.certificate, cls.key).thumbprint
        cls.public_key = x509.load_pem_x509_certificate(cls.certificate.encode()).public_key()

    def build(self, **overrides):
        values = {
            "tenant_id": TENANT_ID,
            "client_id": CLIENT_ID,
            "private_key_pem": self.key,
            "thumbprint": self.thumbprint,
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
        self.assertEqual(claims["exp"], 1_800_000_000 + ASSERTION_LIFETIME_SECONDS)
        self.assertEqual(ASSERTION_LIFETIME_SECONDS, 300)

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
        other_public = serialization.load_pem_private_key(_other_rsa_key_pem().encode(), password=None).public_key()

        with self.assertRaises(jwt.InvalidSignatureError):
            jwt.decode(self.build(), other_public, algorithms=["PS256"], audience=AUDIENCE)

    def test_rs256_is_not_accepted_for_the_assertion(self):
        with self.assertRaises(jwt.InvalidAlgorithmError):
            jwt.decode(self.build(), self.public_key, algorithms=["RS256"], audience=AUDIENCE)

    def test_an_unusable_key_raises_certificate_error(self):
        with self.assertRaises(CertificateError):
            self.build(private_key_pem="not-a-key")
