"""Integration checks for actual OTP records and public outcome projections."""

from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.authn.models import ContactEmail, ContactPhone, Member, PhoneVerificationChallenge, SendVerificationRequest
from apps.authn.models.security import EmailAuthChallenge
from apps.authn.services.email.challenges import AuthChallengeDeliveryError, issue_email_challenge, verify_email_code
from apps.authn.services.send_verification.constants import OP_PASSWORD_RESET_REQUEST_CODE
from apps.authn.services.send_verification.http import serialize_request_status
from apps.authn.services.sms import PhoneVerificationDeliveryError
from apps.authn.tests.send_verification import mint_send_verification
from apps.authn.tests.services.test_send_verification_concurrency import verified_request
from apps.core.services.aws.provider_outcomes import ProviderDeliveryError


@override_settings(
    SEND_VERIFICATION_TEST_AUTOSOLVE=False,
    SEND_VERIFICATION_MODE="enforce",
    SEND_VERIFICATION_COST=10,
    SEND_VERIFICATION_DESTINATION_COOLDOWN_SECONDS=0,
    SEND_VERIFICATION_SMS_DAILY_LIMIT=1000,
)
class SendVerificationDeliveryTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.member = Member.objects.create_user(is_active=True, is_staff=True)
        ContactEmail.objects.create(member=self.member, email_address="admin@example.com", verified=True)
        ContactPhone.objects.create(member=self.member, phone_number="2025550100", region="1-US", verified=True)

    def sms_config(self):
        return SimpleNamespace(render_sms_otp_message=lambda code: f"Code: {code}")

    def test_uncertain_email_keeps_verifiable_otp(self):
        with (
            patch("apps.authn.services.email.challenges._random_code", return_value="123456"),
            patch(
                "apps.authn.services.email.send_email.send_verification_email",
                side_effect=ProviderDeliveryError("timeout", outcome="uncertain"),
            ),
            self.assertRaises(AuthChallengeDeliveryError) as caught,
        ):
            issue_email_challenge(member=self.member, purpose="admin_login", target_email="admin@example.com")
        challenge = EmailAuthChallenge.objects.get(pk=caught.exception.challenge_id)
        self.assertEqual(challenge.status, "pending")
        verified = verify_email_code(purpose="admin_login", target_email="admin@example.com", code="123456")
        self.assertEqual(verified.pk, challenge.pk)

    def test_unknown_sms_reset_is_submitted_and_public_id_verifies_retained_otp(self):
        proof = mint_send_verification(self.client, OP_PASSWORD_RESET_REQUEST_CODE, {"identifier": "2025550100"})
        with (
            patch("apps.authn.services.sms.sns_verify._assert_configured", return_value=self.sms_config()),
            patch("apps.authn.services.sms.sns_verify._random_code", return_value="123456"),
            patch(
                "apps.authn.services.sms.sns_verify._publish_sms",
                side_effect=PhoneVerificationDeliveryError("timeout", outcome="uncertain"),
            ) as publish,
        ):
            response = self.client.post(
                "/authn/password-reset/request-code/", {"identifier": "2025550100", **proof}, format="json"
            )
            replay = self.client.post(
                "/authn/password-reset/request-code/", {"identifier": "2025550100", **proof}, format="json"
            )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["status"], "submitted")
        self.assertEqual(response.data["challenge_id"], proof["send_request_id"])
        self.assertEqual(response.data, replay.data)
        publish.assert_called_once()
        record = SendVerificationRequest.objects.get()
        self.assertEqual(record.status, "unknown")
        self.assertTrue(record.quota_reserved)
        self.assertEqual(PhoneVerificationChallenge.objects.get().status, "sending")
        status_response = self.client.get(f"/authn/send-verification/requests/{proof['send_request_id']}/")
        self.assertEqual(status_response.data["status"], "submitted")
        self.assertEqual(status_response.data["challenge_id"], proof["send_request_id"])
        verified = self.client.post(
            "/authn/password-reset/verify-code/",
            {
                "identifier": "2025550100",
                "challenge_id": proof["send_request_id"],
                "code": "123456",
            },
            format="json",
        )
        self.assertEqual(verified.status_code, 200, verified.data)
        self.assertIn("verification_token", verified.data)

    def test_reset_reference_is_stable_before_and_after_otp_link(self):
        from apps.authn.services.send_verification.guard import consume_and_reserve
        from apps.authn.services.send_verification.hashing import hash_value

        request = verified_request(operation=OP_PASSWORD_RESET_REQUEST_CODE, destination="+12025550100", kind="phone")
        lease = consume_and_reserve(
            request,
            operation=OP_PASSWORD_RESET_REQUEST_CODE,
            destination_kind="phone",
            destination_normalized="+12025550100",
            fingerprint=hash_value("+12025550100"),
            channel="sms",
        )
        before = serialize_request_status(lease.record)
        lease.record.otp_challenge_id = "499738dd-35f8-415e-9b52-1d123f9e0e76"
        lease.record.status = "provider_accepted"
        after = serialize_request_status(lease.record)
        self.assertEqual(before, after)
        self.assertEqual(before["challenge_id"], request.data["send_request_id"])

    def test_unknown_and_ineligible_resets_share_public_shape_and_state(self):
        results = []
        with patch(
            "apps.authn.services.email.send_email.send_verification_email",
            side_effect=ProviderDeliveryError("timeout", outcome="uncertain"),
        ):
            for email in ["admin@example.com", "absent@example.com"]:
                proof = mint_send_verification(self.client, OP_PASSWORD_RESET_REQUEST_CODE, {"email": email})
                response = self.client.post(
                    "/authn/password-reset/request-code/", {"email": email, **proof}, format="json"
                )
                public_status = self.client.get(f"/authn/send-verification/requests/{proof['send_request_id']}/")
                results.append(
                    (
                        response.status_code,
                        response.data.keys(),
                        response.data["message"],
                        public_status.data["status"],
                        public_status.data["code"],
                        public_status.data["http_status"],
                    )
                )
        self.assertEqual(results[0], results[1])
        self.assertEqual(
            set(SendVerificationRequest.objects.values_list("status", flat=True)), {"unknown", "definitely_failed"}
        )

    def test_admin_persists_recovery_before_provider_and_keeps_code_entry_on_unknown(self):
        from django.contrib.sessions.backends.db import SessionStore

        from apps.authn.services.send_verification.constants import OP_ADMIN_LOGIN_REQUEST_CODE

        proof = mint_send_verification(self.client, OP_ADMIN_LOGIN_REQUEST_CODE, {"email": "admin@example.com"})
        session_key = self.client.session.session_key

        def provider_call(**kwargs):
            persisted = SessionStore(session_key=session_key)
            self.assertEqual(persisted["admin_login_step"], "code")
            self.assertEqual(persisted["admin_send_unresolved_request_id"], proof["send_request_id"])
            raise AuthChallengeDeliveryError("timeout", outcome="uncertain")

        with patch("apps.authn.views.admin.login.issue_email_challenge", side_effect=provider_call) as provider:
            response = self.client.post("/admin/login/", {"email": "admin@example.com", **proof})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context["step"], "code")
            self.assertEqual(response.context["send_verification_unresolved_request_id"], proof["send_request_id"])
            self.assertContains(response, "still unresolved")
            self.client.post("/admin/login/", {"action": "resend", **proof})
            provider.assert_called_once()
        SendVerificationRequest.objects.update(status="provider_accepted", result_payload={"detail": "sent"})
        reloaded = self.client.get("/admin/login/")
        self.assertEqual(reloaded.context["step"], "code")
        self.assertNotIn("admin_send_unresolved_request_id", self.client.session)
