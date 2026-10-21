from uuid import uuid4

from django.test import SimpleTestCase

from apps.authn.services.send_verification.hashing import short_destination_hash
from apps.authn.services.send_verification.metrics import emit


class SendVerificationLogPrivacyTests(SimpleTestCase):
    def capture(self, event, **fields):
        with self.assertLogs("apps.authn.send_verification", level="INFO") as logs:
            emit(event, **fields)
        return logs.records[0].getMessage()

    def test_credentials_unknown_fields_and_nested_payloads_are_not_logged(self):
        message = self.capture(
            "send_rejected",
            password="private-password",
            token="private-token",
            request_body={"email": "private@example.com"},
            destination_hash="forged-private-hash",
            code="verification_invalid",
        )
        self.assertEqual(message, "send_verification.send_rejected code=verification_invalid")

    def test_sensitive_data_in_known_fields_is_rejected(self):
        message = self.capture(
            "private-event",
            operation="private-operation",
            status={"private": "payload"},
            code="private-code",
            channel="private-channel",
            request_id="private-id",
            challenge_id="private-id",
            http_status="private-status",
            expired_challenges={"private": "count"},
        )
        self.assertEqual(
            message, "send_verification.unknown channel=unknown code=unknown operation=unknown status=unknown"
        )

    def test_destination_is_only_logged_as_a_pseudonym(self):
        destination = "member@example.com"
        message = self.capture("quota_cooldown", destination=destination, channel="email")
        self.assertNotIn(destination, message)
        self.assertIn(f"destination_hash={short_destination_hash(destination)}", message)

    def test_valid_identifiers_labels_and_counts_are_preserved(self):
        request_id = str(uuid4())
        message = self.capture("send_finalized", request_id=request_id, status="provider_accepted", http_status=202)
        self.assertEqual(
            message,
            f"send_verification.send_finalized http_status=202 request_id={request_id} status=provider_accepted",
        )
        self.assertEqual(
            self.capture("cleanup", expired_challenges=0, deleted_challenges=2, deleted_requests=3),
            "send_verification.cleanup deleted_challenges=2 deleted_requests=3 expired_challenges=0",
        )

    def test_unexpected_objects_are_not_stringified(self):
        class PrivateObject:
            def __str__(self):
                raise AssertionError("Must not stringify private objects")

        private = PrivateObject()
        self.assertEqual(
            self.capture("cleanup", destination=private, request_id=private, deleted_requests=private, extra=private),
            "send_verification.cleanup ",
        )
