import hashlib
import json
from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.authn.models import ContactEmail, Member, SendVerificationRequest
from apps.authn.services.send_verification.constants import FIELD_REQUEST_ID, OP_LOGIN_REQUEST_CODE
from apps.authn.tests.send_verification import mint_send_verification


@override_settings(SEND_VERIFICATION_TEST_AUTOSOLVE=False, SEND_VERIFICATION_MODE="enforce")
class SendVerificationFingerprintTransitionTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.email = "member@example.com"
        member = Member.objects.create_user(password="StrongPass123!", is_active=True)
        ContactEmail.objects.create(member=member, email_address=self.email, email_type="primary", verified=True)

    @patch("apps.authn.services.email.send_email.send_verification_email")
    def test_legacy_fingerprint_retries_fail_closed_and_status_stays_accessible(self, send):
        proof = mint_send_verification(self.client, OP_LOGIN_REQUEST_CODE, {"email": self.email})
        body = {"email": self.email, **proof}
        first = self.client.post("/authn/login/request-code/", body, format="json")
        self.assertEqual(first.status_code, 202)
        record = SendVerificationRequest.objects.get(request_id=proof[FIELD_REQUEST_ID])
        legacy_canonical = json.dumps({"email": self.email}, sort_keys=True, separators=(",", ":"))
        legacy_digest = hashlib.sha256(legacy_canonical.encode()).hexdigest()
        self.assertNotEqual(record.request_fingerprint, legacy_digest)

        for previous_status in SendVerificationRequest.Status.values:
            with self.subTest(previous_status=previous_status):
                SendVerificationRequest.objects.filter(pk=record.pk).update(
                    request_fingerprint=legacy_digest,
                    status=previous_status,
                    idempotency_expires_at=timezone.now() - timedelta(days=1),
                )
                retry = self.client.post("/authn/login/request-code/", body, format="json")
                self.assertEqual(retry.status_code, 409)
                self.assertEqual(retry.data["code"], "send_request_conflict")
                status = self.client.get(f"/authn/send-verification/requests/{proof[FIELD_REQUEST_ID]}/")
                self.assertEqual(status.status_code, 200)
                self.assertEqual(status.data["status"], previous_status)
                record.refresh_from_db()
                self.assertEqual(record.status, previous_status)
                self.assertTrue(record.quota_reserved)
                self.assertEqual(SendVerificationRequest.objects.count(), 1)
                send.assert_called_once()
