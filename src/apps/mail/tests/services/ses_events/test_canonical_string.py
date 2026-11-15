from unittest.mock import patch

from django.test import TestCase

from apps.mail.services.sns import signature as sns_signature
from apps.mail.services.sns.signature import SnsVerificationError


class CanonicalStringTests(TestCase):
    def test_subscription_confirmation_uses_subscription_fields(self):
        envelope = {
            "Type": "SubscriptionConfirmation",
            "Message": "m",
            "MessageId": "id",
            "SubscribeURL": "https://example.com",
            "Timestamp": "t",
            "Token": "tok",
            "TopicArn": "arn",
        }
        canonical = sns_signature._canonical_string(envelope)
        self.assertIn(b"SubscribeURL", canonical)
        self.assertIn(b"Token", canonical)

    def test_unknown_type_raises(self):
        with self.assertRaisesMessage(SnsVerificationError, "Unknown SNS Type"):
            sns_signature._canonical_string({"Type": "Weird"})

    def test_notification_skips_optional_missing_subject(self):
        envelope = {
            "Type": "Notification",
            "Message": "m",
            "MessageId": "id",
            "Timestamp": "t",
            "TopicArn": "arn",
            # Subject deliberately absent
        }
        canonical = sns_signature._canonical_string(envelope)
        self.assertNotIn(b"Subject", canonical)

    def test_missing_required_field_raises(self):
        envelope = {
            "Type": "Notification",
            "Message": "m",
            # MessageId missing
            "Timestamp": "t",
            "TopicArn": "arn",
            "Subject": "s",
        }
        with self.assertRaisesMessage(SnsVerificationError, "Missing field"):
            sns_signature._canonical_string(envelope)


class FetchCertTests(TestCase):
    def setUp(self):
        sns_signature._CERT_CACHE.clear()

    def tearDown(self):
        sns_signature._CERT_CACHE.clear()

    def test_fetch_downloads_and_caches_pem(self):
        cert_url = "https://sns.us-west-2.amazonaws.com/cert.pem"

        with patch("apps.mail.services.sns.signature.fetch_sns_https", return_value=b"PEM-BYTES") as mock_fetch:
            pem = sns_signature._fetch_cert(cert_url)

        self.assertEqual(pem, b"PEM-BYTES")
        self.assertEqual(sns_signature._CERT_CACHE[cert_url], b"PEM-BYTES")
        mock_fetch.assert_called_once_with(cert_url)

    def test_fetch_evicts_cache_when_full(self):
        cert_url = "https://sns.us-west-2.amazonaws.com/cert.pem"
        for i in range(sns_signature._CERT_CACHE_MAX):
            sns_signature._CERT_CACHE[f"https://sns.amazonaws.com/{i}.pem"] = b"old"

        with patch("apps.mail.services.sns.signature.fetch_sns_https", return_value=b"NEW-PEM"):
            pem = sns_signature._fetch_cert(cert_url)

        self.assertEqual(pem, b"NEW-PEM")
        # Cache was cleared then repopulated with only the new entry.
        self.assertEqual(sns_signature._CERT_CACHE, {cert_url: b"NEW-PEM"})

    def test_fetch_rejects_disallowed_host(self):
        with self.assertRaises(SnsVerificationError):
            sns_signature._fetch_cert("https://evil.example.com/cert.pem")
