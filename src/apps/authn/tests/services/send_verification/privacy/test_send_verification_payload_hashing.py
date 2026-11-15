from django.test import SimpleTestCase, override_settings
from django.utils.crypto import salted_hmac

from apps.authn.services.send_verification.hashing import fingerprint_payload


@override_settings(SECRET_KEY="test-payload-fingerprint-key")
class SendVerificationPayloadHashingTests(SimpleTestCase):
    def test_fingerprint_is_keyed_and_domain_separated(self):
        self.assertEqual(
            fingerprint_payload({"email": "member@example.com"}),
            salted_hmac(
                "send-verification.payload-fingerprint", '{"email":"member@example.com"}', algorithm="sha256"
            ).hexdigest(),
        )
        self.assertNotEqual(
            fingerprint_payload({"email": "member@example.com"}),
            salted_hmac("another-purpose", '{"email":"member@example.com"}', algorithm="sha256").hexdigest(),
        )

    def test_reordered_payloads_produce_the_same_fingerprint(self):
        first = {"email": "member@example.com", "context": {"name": "姓名", "subscribe": True}}
        second = {"context": {"subscribe": True, "name": "姓名"}, "email": "member@example.com"}
        self.assertEqual(fingerprint_payload(first), fingerprint_payload(second))
        self.assertRegex(fingerprint_payload(first), r"^[a-f0-9]{64}$")

    def test_private_field_changes_still_prevent_request_id_reuse(self):
        first = {"email": "member@example.com", "password_digest": "first-keyed-password-digest"}
        changed = {**first, "password_digest": "different-keyed-password-digest"}
        self.assertNotEqual(fingerprint_payload(first), fingerprint_payload(changed))

    def test_key_rotation_changes_fingerprint(self):
        original = fingerprint_payload({"email": "member@example.com"})
        with override_settings(SECRET_KEY="rotated-test-fingerprint-key"):
            self.assertNotEqual(original, fingerprint_payload({"email": "member@example.com"}))
