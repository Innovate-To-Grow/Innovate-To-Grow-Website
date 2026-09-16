"""Real authentication and business-context regressions for protected sends."""

from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.authn.models import (
    ContactEmail,
    ContactPhone,
    EmailAuthChallenge,
    Member,
    PhoneVerificationChallenge,
    SendVerificationChallenge,
    SendVerificationRequest,
)
from apps.authn.services.send_verification.constants import (
    FIELD_CHALLENGE_ID,
    FIELD_PAYLOAD,
    FIELD_REQUEST_ID,
    OP_CHANGE_PASSWORD_REQUEST_CODE,
    OP_CONTACT_EMAIL_CREATE,
    OP_CONTACT_EMAIL_REQUEST_VERIFICATION,
    OP_CONTACT_PHONE_REQUEST_VERIFICATION,
    OP_DELETE_ACCOUNT_REQUEST_CODE,
    OP_EMAIL_AUTH_REQUEST_CODE,
    OP_EVENT_SEND_PHONE_CODE,
    OP_LOGIN_REQUEST_CODE,
    OP_PASSWORD_RESET_REQUEST_CODE,
    OP_PHONE_AUTH_REQUEST_CODE,
    OP_REGISTER,
    OP_REGISTER_RESEND_CODE,
)
from apps.authn.tests.send_verification import CHALLENGE_PATH, mint_send_verification
from apps.event.tests.helpers import make_event


@override_settings(SEND_VERIFICATION_TEST_AUTOSOLVE=False, SEND_VERIFICATION_MODE="enforce")
class SendVerificationContextTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.member = Member.objects.create_user(password="StrongPass123!", is_active=True)
        self.email = "context@example.com"
        ContactEmail.objects.create(member=self.member, email_address=self.email, email_type="primary", verified=True)
        self.contact = ContactEmail.objects.create(
            member=self.member, email_address="pending@example.com", email_type="secondary"
        )
        self.phone = ContactPhone.objects.create(member=self.member, phone_number="2025550100", verified=True)
        self.pending_phone = ContactPhone.objects.create(member=self.member, phone_number="2025550101")
        self.token = str(RefreshToken.for_user(self.member).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")

    @patch("apps.authn.services.email.send_email.send_verification_email")
    def test_public_send_and_status_keep_session_with_real_bearer_token(self, send):
        proof = mint_send_verification(self.client, OP_LOGIN_REQUEST_CODE, {"email": self.email})
        challenge = SendVerificationChallenge.objects.get(pk=proof[FIELD_CHALLENGE_ID])
        self.assertEqual(challenge.principal_type, "session")
        response = self.client.post("/authn/login/request-code/", {"email": self.email, **proof}, format="json")
        self.assertEqual(response.status_code, 202, response.data)
        send.assert_called_once()
        status_url = f"/authn/send-verification/requests/{proof[FIELD_REQUEST_ID]}/"
        self.assertEqual(self.client.get(status_url).data["status"], "provider_accepted")
        # Public request ownership survives access-token expiry and removal.
        self.client.credentials(HTTP_AUTHORIZATION="Bearer expired-or-invalid")
        self.assertEqual(self.client.get(status_url).status_code, 200)
        self.client.credentials()
        self.assertEqual(self.client.get(status_url).status_code, 200)
        stranger = APIClient()
        stranger.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")
        self.assertNotEqual(stranger.get(status_url).status_code, 200)

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


@override_settings(
    SEND_VERIFICATION_TEST_AUTOSOLVE=False, SEND_VERIFICATION_MODE="enforce", REQUIRE_ENCRYPTED_PASSWORDS=False
)
class SendVerificationCoverageTests(APITestCase):
    """Exercise every API send gate without the legacy automatic-proof helper."""

    setUp = SendVerificationContextTests.setUp

    def _sending_cases(self):
        event = make_event(registration_open=True, collect_phone=True, verify_phone=True)
        return (
            (OP_EMAIL_AUTH_REQUEST_CODE, "/authn/email-auth/request-code/", {"email": "new@example.com"}, {}),
            (OP_PHONE_AUTH_REQUEST_CODE, "/authn/phone-auth/request-code/", {"phone_number": "2025550100"}, {}),
            (OP_LOGIN_REQUEST_CODE, "/authn/login/request-code/", {"email": self.email}, {}),
            (
                OP_REGISTER,
                "/authn/register/",
                {
                    "email": "new@example.com",
                    "password": "StrongPass123!",
                    "password_confirm": "StrongPass123!",
                    "first_name": "Test",
                    "last_name": "User",
                    "organization": "University",
                },
                {},
            ),
            (OP_REGISTER_RESEND_CODE, "/authn/register/resend-code/", {"email": "new@example.com"}, {}),
            (OP_PASSWORD_RESET_REQUEST_CODE, "/authn/password-reset/request-code/", {"identifier": self.email}, {}),
            (OP_CHANGE_PASSWORD_REQUEST_CODE, "/authn/change-password/request-code/", {}, {}),
            (OP_DELETE_ACCOUNT_REQUEST_CODE, "/authn/delete-account/request-code/", {}, {}),
            (OP_CONTACT_EMAIL_CREATE, "/authn/contact-emails/", {"email_address": "new@example.com"}, {}),
            (
                OP_CONTACT_EMAIL_REQUEST_VERIFICATION,
                f"/authn/contact-emails/{self.contact.pk}/request-verification/",
                {},
                {"contact_id": str(self.contact.pk)},
            ),
            (
                OP_CONTACT_PHONE_REQUEST_VERIFICATION,
                f"/authn/contact-phones/{self.pending_phone.pk}/request-verification/",
                {},
                {"contact_id": str(self.pending_phone.pk)},
            ),
            (
                OP_EVENT_SEND_PHONE_CODE,
                "/event/send-phone-code/",
                {"phone": "2025550100", "event_slug": event.slug},
                {},
            ),
        )

    @patch("apps.authn.services.sms.sns_verify._publish_sms")
    @patch("apps.authn.services.email.send_email.send_verification_email")
    def test_every_api_gate_rejects_bad_proofs_before_side_effects(self, email, sms):
        cases = self._sending_cases()
        models = (
            Member,
            ContactEmail,
            ContactPhone,
            EmailAuthChallenge,
            PhoneVerificationChallenge,
            SendVerificationRequest,
        )
        baseline = [model.objects.count() for model in models]
        errors = {
            "missing": "verification_required",
            "forged": "verification_invalid",
            "expired": "verification_expired",
            "consumed": "verification_consumed",
            "wrong_context": "verification_context_mismatch",
        }
        for operation, path, data, extra in cases:
            for variant, expected in errors.items():
                with self.subTest(operation=operation, variant=variant):
                    cache.clear()
                    proof = {}
                    if variant != "missing":
                        proof = mint_send_verification(self.client, operation, {**data, **extra})
                        row = SendVerificationChallenge.objects.filter(pk=proof[FIELD_CHALLENGE_ID])
                        if variant == "forged":
                            proof[FIELD_PAYLOAD] = "malformed"
                        elif variant == "expired":
                            row.update(expires_at=timezone.now() - timedelta(seconds=1))
                        elif variant == "consumed":
                            row.update(status="consumed")
                        elif variant == "wrong_context":
                            row.update(destination_normalized="different@example.com")
                    response = self.client.post(path, {**data, **proof}, format="json")
                    self.assertEqual(response.status_code, 400, response.data)
                    self.assertEqual(response.data.get("code"), expected, response.data)
                    self.assertEqual([model.objects.count() for model in models], baseline)
        email.assert_not_called()
        sms.assert_not_called()
