from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.authn.models import ContactEmail, Member, SendVerificationChallenge
from apps.authn.services.send_verification.constants import (
    FIELD_CHALLENGE_ID,
    FIELD_PAYLOAD,
    FIELD_REQUEST_ID,
    OP_EMAIL_AUTH_REQUEST_CODE,
    OP_LOGIN_REQUEST_CODE,
)
from apps.authn.tests.send_verification import mint_send_verification


@override_settings(SEND_VERIFICATION_TEST_AUTOSOLVE=False, SEND_VERIFICATION_MODE="enforce")
class SendVerificationAPITests(APITestCase):
    def setUp(self):
        cache.clear()
        self.member = Member.objects.create_user(password="StrongPass123!", is_active=True)
        self.email = "member@example.com"
        ContactEmail.objects.create(
            member=self.member,
            email_address=self.email,
            email_type="primary",
            verified=True,
        )

    def test_missing_proof_does_not_send(self):
        with patch("apps.authn.services.email.send_email.send_verification_email") as mock_send:
            response = self.client.post(
                "/authn/login/request-code/",
                {"email": self.email},
                format="json",
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "verification_required")
        mock_send.assert_not_called()

    def test_forged_payload_does_not_send(self):
        proof = mint_send_verification(self.client, OP_LOGIN_REQUEST_CODE, {"email": self.email})
        proof[FIELD_PAYLOAD] = "not-a-valid-payload"
        with patch("apps.authn.services.email.send_email.send_verification_email") as mock_send:
            response = self.client.post(
                "/authn/login/request-code/",
                {"email": self.email, **proof},
                format="json",
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "verification_invalid")
        mock_send.assert_not_called()

    def test_wrong_destination_does_not_send(self):
        proof = mint_send_verification(self.client, OP_LOGIN_REQUEST_CODE, {"email": self.email})
        with patch("apps.authn.services.email.send_email.send_verification_email") as mock_send:
            response = self.client.post(
                "/authn/login/request-code/",
                {"email": "other@example.com", **proof},
                format="json",
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "verification_context_mismatch")
        mock_send.assert_not_called()

    def test_wrong_operation_does_not_send(self):
        proof = mint_send_verification(self.client, OP_EMAIL_AUTH_REQUEST_CODE, {"email": self.email})
        with patch("apps.authn.services.email.send_email.send_verification_email") as mock_send:
            response = self.client.post(
                "/authn/login/request-code/",
                {"email": self.email, **proof},
                format="json",
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "verification_context_mismatch")
        mock_send.assert_not_called()

    def test_expired_challenge_does_not_send(self):
        proof = mint_send_verification(self.client, OP_LOGIN_REQUEST_CODE, {"email": self.email})
        SendVerificationChallenge.objects.filter(pk=proof[FIELD_CHALLENGE_ID]).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        with patch("apps.authn.services.email.send_email.send_verification_email") as mock_send:
            response = self.client.post(
                "/authn/login/request-code/",
                {"email": self.email, **proof},
                format="json",
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "verification_expired")
        mock_send.assert_not_called()

    @patch("apps.authn.services.email.send_email.send_verification_email")
    def test_consumed_challenge_cannot_send_again(self, mock_send):
        proof = mint_send_verification(self.client, OP_LOGIN_REQUEST_CODE, {"email": self.email})
        first = self.client.post("/authn/login/request-code/", {"email": self.email, **proof}, format="json")
        self.assertEqual(first.status_code, 202)
        proof[FIELD_REQUEST_ID] = str(uuid4())
        second = self.client.post("/authn/login/request-code/", {"email": self.email, **proof}, format="json")
        self.assertEqual(second.status_code, 400)
        self.assertEqual(second.data["code"], "verification_consumed")
        mock_send.assert_called_once()

    @patch("apps.authn.services.email.send_email.send_verification_email")
    def test_valid_proof_sends_and_replay_returns_state(self, mock_send):
        proof = mint_send_verification(self.client, OP_LOGIN_REQUEST_CODE, {"email": self.email})
        first = self.client.post(
            "/authn/login/request-code/",
            {"email": self.email, **proof},
            format="json",
        )
        self.assertEqual(first.status_code, 202)
        mock_send.assert_called_once()
        second = self.client.post(
            "/authn/login/request-code/",
            {"email": self.email, **proof},
            format="json",
        )
        self.assertEqual(second.status_code, 202)
        mock_send.assert_called_once()

    @patch("apps.authn.services.email.send_email.send_verification_email")
    def test_conflicting_request_id_is_rejected(self, mock_send):
        first_proof = mint_send_verification(self.client, OP_LOGIN_REQUEST_CODE, {"email": self.email})
        self.client.post("/authn/login/request-code/", {"email": self.email, **first_proof}, format="json")
        other_email = "other@example.com"
        other = mint_send_verification(self.client, OP_LOGIN_REQUEST_CODE, {"email": other_email})
        other[FIELD_REQUEST_ID] = first_proof[FIELD_REQUEST_ID]
        response = self.client.post(
            "/authn/login/request-code/",
            {"email": other_email, **other},
            format="json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "send_request_conflict")

    def test_pause_fails_closed(self):
        with override_settings(SEND_VERIFICATION_MODE="pause"):
            proof = None
            try:
                proof = mint_send_verification(self.client, OP_LOGIN_REQUEST_CODE, {"email": self.email})
            except AssertionError:
                proof = {
                    FIELD_CHALLENGE_ID: str(uuid4()),
                    FIELD_PAYLOAD: "x",
                    FIELD_REQUEST_ID: str(uuid4()),
                }
            with patch("apps.authn.services.email.send_email.send_verification_email") as mock_send:
                response = self.client.post(
                    "/authn/login/request-code/",
                    {"email": self.email, **(proof or {})},
                    format="json",
                )
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.data["code"], "send_paused")
            mock_send.assert_not_called()

    def test_missing_hmac_fails_closed(self):
        with override_settings(SEND_VERIFICATION_HMAC_SECRET="", SEND_VERIFICATION_HMAC_KEY_SECRET=""):
            response = self.client.post(
                "/authn/send-verification/challenge/",
                {"operation": OP_LOGIN_REQUEST_CODE, "email": self.email},
                format="json",
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "verification_unavailable")

    def test_status_lookup_does_not_enumerate(self):
        response = self.client.get(f"/authn/send-verification/requests/{uuid4()}/")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "verification_invalid")

    def test_protected_public_sends_require_proof(self):
        paths = (
            ("/authn/email-auth/request-code/", {"email": self.email}),
            ("/authn/phone-auth/request-code/", {"phone_number": "2025550100", "region": "1-US"}),
            ("/authn/register/resend-code/", {"email": self.email}),
            ("/authn/password-reset/request-code/", {"email": self.email}),
        )
        for path, body in paths:
            with self.subTest(path=path):
                with patch("apps.authn.services.email.send_email.send_verification_email") as mock_send:
                    with patch("apps.authn.services.sms.start_phone_verification") as mock_sms:
                        response = self.client.post(path, body, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.data["code"], "verification_required")
                mock_send.assert_not_called()
                mock_sms.assert_not_called()
