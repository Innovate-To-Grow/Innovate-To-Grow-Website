import hashlib

from django.test import SimpleTestCase, override_settings
from django.utils.crypto import salted_hmac

from apps.authn.services.send_verification.hashing import short_destination_hash


@override_settings(SECRET_KEY="test-destination-pseudonym-key")
class SendVerificationDestinationHashingTests(SimpleTestCase):
    def test_destination_pseudonym_is_keyed_and_domain_separated(self):
        destination = "member@example.com"
        digest = short_destination_hash(destination)
        self.assertEqual(
            digest,
            salted_hmac("send-verification.destination-log", destination, algorithm="sha256").hexdigest()[:12],
        )
        self.assertNotEqual(digest, hashlib.sha256(destination.encode()).hexdigest()[:12])
        self.assertNotEqual(digest, salted_hmac("another-purpose", destination, algorithm="sha256").hexdigest()[:12])

    def test_pseudonym_preserves_stable_short_log_format(self):
        digest = short_destination_hash("member@example.com")
        self.assertRegex(digest, r"^[a-f0-9]{12}$")
        self.assertEqual(digest, short_destination_hash("member@example.com"))
        self.assertNotEqual(digest, short_destination_hash("other@example.com"))

    def test_key_rotation_changes_pseudonyms(self):
        digest = short_destination_hash("member@example.com")
        with override_settings(SECRET_KEY="rotated-test-destination-key"):
            self.assertNotEqual(digest, short_destination_hash("member@example.com"))

    def test_unicode_destinations_are_supported(self):
        self.assertRegex(short_destination_hash("member@例子.example"), r"^[a-f0-9]{12}$")
