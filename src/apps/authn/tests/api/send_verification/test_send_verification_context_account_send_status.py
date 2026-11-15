from datetime import timedelta
from unittest.mock import patch

from django.test import override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.authn.models import (
    Member,
    SendVerificationChallenge,
    SendVerificationRequest,
)
from apps.authn.services.send_verification.rules.constants import (
    FIELD_CHALLENGE_ID,
    FIELD_REQUEST_ID,
    OP_CHANGE_PASSWORD_REQUEST_CODE,
    OP_EVENT_SEND_PHONE_CODE,
    OP_LOGIN_REQUEST_CODE,
    OP_PASSWORD_RESET_REQUEST_CODE,
    OP_REGISTER,
)
from apps.authn.tests.api.send_verification.test_send_verification_context import _SendVerificationContextCase
from apps.authn.tests.helpers.send_verification import CHALLENGE_PATH, mint_send_verification


@override_settings(SEND_VERIFICATION_TEST_AUTOSOLVE=False, SEND_VERIFICATION_MODE="enforce")
class SendVerificationContextTests(_SendVerificationContextCase):
    @patch("apps.authn.services.email.send_email.send_verification_email")
    def test_account_send_and_status_require_same_real_member(self, send):
        proof = mint_send_verification(self.client, OP_CHANGE_PASSWORD_REQUEST_CODE, {})
        challenge = SendVerificationChallenge.objects.get(pk=proof[FIELD_CHALLENGE_ID])
        self.assertEqual(challenge.principal_type, "member")
        response = self.client.post("/authn/change-password/request-code/", proof, format="json")
        self.assertEqual(response.status_code, 202, response.data)
        send.assert_called_once()
        url = f"/authn/send-verification/requests/{proof[FIELD_REQUEST_ID]}/"
        new_browser = APIClient()
        new_browser.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")
        self.assertEqual(new_browser.get(url).status_code, 200)
        new_browser.credentials()
        self.assertNotEqual(new_browser.get(url).status_code, 200)
        other = Member.objects.create_user(password="StrongPass123!", is_active=True)
        new_browser.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(other).access_token}")
        self.assertNotEqual(new_browser.get(url).status_code, 200)

    def test_expired_jwt_is_401_before_protected_challenge_creation(self):
        token = RefreshToken.for_user(self.member).access_token
        token.set_exp(lifetime=timedelta(seconds=-60))
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = self.client.post(CHALLENGE_PATH, {"operation": OP_CHANGE_PASSWORD_REQUEST_CODE}, format="json")
        self.assertEqual(response.status_code, 401)
        self.assertFalse(SendVerificationChallenge.objects.exists())

    def test_public_challenge_ignores_invalid_optional_bearer(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer invalid")
        response = self.client.post(
            CHALLENGE_PATH, {"operation": OP_LOGIN_REQUEST_CODE, "email": self.email}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)

    def test_public_challenge_rejects_admin_operations(self):
        response = self.client.post(
            CHALLENGE_PATH, {"operation": "admin.login.request_code", "email": self.email}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_challenge_payload_must_be_an_object(self):
        response = self.client.post(CHALLENGE_PATH, ["unexpected"], format="json")
        self.assertEqual(response.status_code, 400)

    def test_oversized_destination_is_rejected_before_database_insert(self):
        response = self.client.post(
            CHALLENGE_PATH,
            {"operation": OP_LOGIN_REQUEST_CODE, "destination": "a" * 255},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(SendVerificationChallenge.objects.exists())

    def test_event_challenge_uses_us_policy_even_with_other_region(self):
        proof = mint_send_verification(
            self.client, OP_EVENT_SEND_PHONE_CODE, {"phone": "2025550100", "region": "44-GB"}
        )
        challenge = SendVerificationChallenge.objects.get(pk=proof[FIELD_CHALLENGE_ID])
        self.assertEqual(challenge.destination_normalized, "+12025550100")

    @patch("apps.authn.services.email.send_email.send_verification_email")
    @patch("apps.authn.services.sms.sns_verify._publish_sms")
    def test_extra_destination_cannot_turn_sms_into_email_budget(self, sms, email):
        proof = mint_send_verification(self.client, OP_PASSWORD_RESET_REQUEST_CODE, {"email": self.email})
        with override_settings(SEND_VERIFICATION_SMS_DAILY_LIMIT=None):
            response = self.client.post(
                "/authn/password-reset/request-code/",
                {"email": self.phone.phone_number, "destination": self.email, **proof},
                format="json",
            )
        self.assertEqual(response.status_code, 503, response.data)
        sms.assert_not_called()
        email.assert_not_called()
        self.assertFalse(SendVerificationRequest.objects.exists())

    @patch("apps.authn.services.email.send_email.send_verification_email")
    def test_change_password_ignores_raw_destination_alias(self, send):
        proof = mint_send_verification(self.client, OP_CHANGE_PASSWORD_REQUEST_CODE, {})
        response = self.client.post(
            "/authn/change-password/request-code/", {"destination": "attacker@example.com", **proof}, format="json"
        )
        self.assertEqual(response.status_code, 202, response.data)
        self.assertEqual(send.call_args.kwargs["recipient"], self.email)
        record = SendVerificationRequest.objects.get(request_id=proof[FIELD_REQUEST_ID])
        self.assertEqual(record.destination_normalized, self.email)

    @override_settings(REQUIRE_ENCRYPTED_PASSWORDS=False)
    @patch("apps.authn.services.email.send_email.send_verification_email")
    def test_registration_request_id_binds_to_the_validated_password(self, send):
        data = {
            "email": "new-registration@example.com",
            "password": "StrongPass123!",
            "password_confirm": "StrongPass123!",
            "first_name": "Test",
            "last_name": "User",
            "organization": "University",
        }
        proof = mint_send_verification(self.client, OP_REGISTER, data)
        first = self.client.post("/authn/register/", {**data, **proof}, format="json")
        self.assertEqual(first.status_code, 202, first.data)
        replay = self.client.post("/authn/register/", {**data, **proof}, format="json")
        self.assertEqual(replay.status_code, 202, replay.data)
        changed = {**data, "password": "AnotherPass123!", "password_confirm": "AnotherPass123!"}
        conflict = self.client.post("/authn/register/", {**changed, **proof}, format="json")
        self.assertEqual(conflict.status_code, 409, conflict.data)
        self.assertEqual(conflict.data["code"], "send_request_conflict")
        send.assert_called_once()
