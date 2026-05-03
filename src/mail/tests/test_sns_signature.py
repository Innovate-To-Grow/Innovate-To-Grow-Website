"""Tests for mail.services.sns_signature.

Generates a self-signed RSA cert on the fly, signs a canonical SNS payload,
and asserts verify_sns_message accepts it. Tampering with any signed field
must flip it to an error.
"""

import base64
import datetime as dt
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID
from django.test import TestCase

from mail.services import sns_signature
from mail.services.sns_signature import SnsVerificationError, verify_sns_message


def _make_self_signed_cert() -> tuple[bytes, rsa.RSAPrivateKey]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "sns.amazonaws.com")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(dt.datetime.utcnow() - dt.timedelta(days=1))
        .not_valid_after(dt.datetime.utcnow() + dt.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM), key


def _sign_envelope(envelope: dict, key: rsa.RSAPrivateKey, algo=hashes.SHA256()) -> dict:
    """Sign an envelope in the same canonical form the verifier expects."""
    from mail.services.sns_signature import _canonical_string

    canonical = _canonical_string(envelope)
    signature = key.sign(canonical, padding.PKCS1v15(), algo)
    envelope = dict(envelope)
    envelope["Signature"] = base64.b64encode(signature).decode("ascii")
    return envelope


def _base_notification() -> dict:
    return {
        "Type": "Notification",
        "MessageId": "sns-abc",
        "TopicArn": "arn:aws:sns:us-west-2:123:ses-events",
        "Subject": "",
        "Message": "{}",
        "Timestamp": "2026-04-22T12:00:00.000Z",
        "SignatureVersion": "2",
        "SigningCertURL": "https://sns.us-west-2.amazonaws.com/cert.pem",
    }


class VerifySnsMessageTests(TestCase):
    def setUp(self):
        self.pem, self.key = _make_self_signed_cert()
        sns_signature._CERT_CACHE.clear()
        sns_signature._CERT_CACHE["https://sns.us-west-2.amazonaws.com/cert.pem"] = self.pem

    def tearDown(self):
        sns_signature._CERT_CACHE.clear()

    def test_valid_v2_signature_passes(self):
        envelope = _sign_envelope(_base_notification(), self.key)
        verify_sns_message(envelope)  # should not raise

    def test_valid_v1_signature_passes(self):
        envelope = _base_notification()
        envelope["SignatureVersion"] = "1"
        envelope = _sign_envelope(envelope, self.key, algo=hashes.SHA1())
        verify_sns_message(envelope)  # should not raise

    def test_tampered_message_fails(self):
        envelope = _sign_envelope(_base_notification(), self.key)
        envelope["Message"] = '{"tampered": true}'
        with self.assertRaises(SnsVerificationError):
            verify_sns_message(envelope)

    def test_non_amazonaws_cert_url_is_rejected(self):
        envelope = _base_notification()
        envelope["SigningCertURL"] = "https://evil.example.com/cert.pem"
        envelope = _sign_envelope(envelope, self.key)
        sns_signature._CERT_CACHE.clear()  # would otherwise short-circuit the host check
        with self.assertRaises(SnsVerificationError) as ctx:
            verify_sns_message(envelope)
        self.assertIn("host is not allowed", str(ctx.exception))

    def test_amazonaws_lookalike_cert_url_is_rejected(self):
        envelope = _base_notification()
        envelope["SigningCertURL"] = "https://sns.us-west-2.amazonaws.com.evil.example/cert.pem"
        envelope = _sign_envelope(envelope, self.key)
        sns_signature._CERT_CACHE.clear()
        with self.assertRaises(SnsVerificationError) as ctx:
            verify_sns_message(envelope)
        self.assertIn("host is not allowed", str(ctx.exception))

    def test_cert_url_with_credentials_is_rejected(self):
        envelope = _base_notification()
        envelope["SigningCertURL"] = "https://user:pass@sns.us-west-2.amazonaws.com/cert.pem"
        envelope = _sign_envelope(envelope, self.key)
        sns_signature._CERT_CACHE.clear()
        with self.assertRaises(SnsVerificationError) as ctx:
            verify_sns_message(envelope)
        self.assertIn("credentials", str(ctx.exception))

    def test_http_cert_url_is_rejected(self):
        envelope = _base_notification()
        envelope["SigningCertURL"] = "http://sns.us-west-2.amazonaws.com/cert.pem"
        envelope = _sign_envelope(envelope, self.key)
        sns_signature._CERT_CACHE.clear()
        with self.assertRaises(SnsVerificationError) as ctx:
            verify_sns_message(envelope)
        self.assertIn("https", str(ctx.exception))

    def test_topic_arn_allowlist_enforced(self):
        envelope = _sign_envelope(_base_notification(), self.key)
        with self.assertRaises(SnsVerificationError) as ctx:
            verify_sns_message(envelope, allowed_topic_arns={"arn:aws:sns:us-west-2:123:other-topic"})
        self.assertIn("TopicArn not allowed", str(ctx.exception))

    def test_topic_arn_allowlist_match_passes(self):
        envelope = _sign_envelope(_base_notification(), self.key)
        verify_sns_message(envelope, allowed_topic_arns={envelope["TopicArn"]})

    def test_unsupported_signature_version(self):
        envelope = _base_notification()
        envelope["SignatureVersion"] = "99"
        envelope = _sign_envelope(envelope, self.key)
        with self.assertRaises(SnsVerificationError) as ctx:
            verify_sns_message(envelope)
        self.assertIn("SignatureVersion", str(ctx.exception))

    def test_cert_fetch_happens_only_once_for_repeated_urls(self):
        envelope = _sign_envelope(_base_notification(), self.key)
        sns_signature._CERT_CACHE.clear()
        sns_signature._CERT_CACHE["https://sns.us-west-2.amazonaws.com/cert.pem"] = self.pem
        with patch("mail.services.sns_signature.urllib.request.urlopen") as mock_urlopen:
            verify_sns_message(envelope)
            verify_sns_message(envelope)
            mock_urlopen.assert_not_called()
