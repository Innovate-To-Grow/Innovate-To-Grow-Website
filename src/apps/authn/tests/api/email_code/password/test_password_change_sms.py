"""Password create/change via SMS verification, and channel selection.

Covers the phone-only initial-password path (SMS OTP -> token -> confirm), the
OTP failure modes (wrong / throttled / reused / expired), and the
verification-channel selection order (verified primary email -> any verified
email -> verified phone via SMS).
"""

import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APITestCase

from apps.authn.models import (
    ContactPhone,
    EmailAuthChallenge,
)
from apps.authn.services import (
    PhoneVerificationDeliveryError,
)

Member = get_user_model()

REQUEST_URL = "/authn/change-password/request-code/"
VERIFY_URL = "/authn/change-password/verify-code/"
CONFIRM_URL = "/authn/change-password/confirm/"
RESET_REQUEST_URL = "/authn/password-reset/request-code/"
RESET_VERIFY_URL = "/authn/password-reset/verify-code/"
NEW_PASSWORD = "SmsCreatedPass123!"


class _PhoneOnlyPasswordCreateViaSmsCase(APITestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.member = Member.objects.create_user(is_active=True, first_name="Pat", last_name="Phone")
        self.member.set_unusable_password()
        self.member.save()
        self.phone = ContactPhone.objects.create(
            member=self.member, phone_number="2095551234", region="1-US", verified=True
        )
        self.client.force_authenticate(user=self.member)

    def _request_and_verify(self, mock_start, mock_check):
        mock_start.return_value = {"status": "pending", "challenge_id": str(uuid.uuid4())}
        mock_check.return_value = (object(), "approved")
        request = self.client.post(REQUEST_URL, {}, format="json")
        self.assertEqual(request.status_code, 202)
        self.assertEqual(request.data["channel"], "sms")
        verify = self.client.post(VERIFY_URL, {"code": "123456"}, format="json")
        self.assertEqual(verify.status_code, 200)
        return verify.data["verification_token"]


@patch("apps.authn.services.account.sms_password._check_phone_verification")
@patch("apps.authn.services.account.sms_password.start_phone_verification")
class PhoneOnlyPasswordCreateViaSmsTests(_PhoneOnlyPasswordCreateViaSmsCase):
    """A phone-only account (verified phone, no email, unusable password)."""

    def test_request_selects_sms_and_sends_code(self, mock_start, _mock_check):
        challenge_id = str(uuid.uuid4())
        mock_start.return_value = {"status": "pending", "challenge_id": challenge_id}
        response = self.client.post(REQUEST_URL, {}, format="json")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["channel"], "sms")
        self.assertEqual(response.data["challenge_id"], challenge_id)
        self.assertIn("4", response.data["destination"])  # last 4 digits surfaced, rest masked
        mock_start.assert_called_once_with(
            "+12095551234",
            purpose=EmailAuthChallenge.Purpose.PASSWORD_CHANGE,
            member=self.member,
            context_identifier=f"{EmailAuthChallenge.Purpose.PASSWORD_CHANGE}:{self.member.pk}",
        )

    def test_password_change_sms_delivery_failure_is_not_reported_as_sent(self, mock_start, _mock_check):
        mock_start.side_effect = PhoneVerificationDeliveryError("provider rejected", outcome="permanent")

        response = self.client.post(REQUEST_URL, {}, format="json")

        self.assertEqual(response.status_code, 503)
        self.assertNotEqual(response.data.get("message"), "Verification code sent.")

    def test_password_reset_request_returns_enumeration_safe_challenge_id(self, mock_start, _mock_check):
        challenge_id = str(uuid.uuid4())
        mock_start.return_value = {"status": "pending", "challenge_id": challenge_id}

        response = self.client.post(
            RESET_REQUEST_URL,
            {"identifier": "2095551234"},
            format="json",
        )

        self.assertEqual(response.status_code, 202)
        from apps.authn.models import SendVerificationRequest

        record = SendVerificationRequest.objects.get(request_id=response.data["challenge_id"])
        self.assertEqual(record.otp_challenge_id, challenge_id)
        self.assertEqual(response.data["status"], "submitted")
        mock_start.assert_called_once_with(
            "+12095551234",
            purpose=EmailAuthChallenge.Purpose.PASSWORD_RESET,
            member=self.member,
            context_identifier=f"{EmailAuthChallenge.Purpose.PASSWORD_RESET}:{self.member.pk}",
        )

    def test_password_reset_verify_accepts_challenge_id(self, _mock_start, mock_check):
        challenge_id = uuid.uuid4()
        mock_check.return_value = (object(), "approved")

        response = self.client.post(
            RESET_VERIFY_URL,
            {
                "identifier": "2095551234",
                "code": "123456",
                "challenge_id": str(challenge_id),
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        mock_check.assert_called_once_with(
            phone_number="+12095551234",
            code="123456",
            challenge_id=challenge_id,
            purpose=EmailAuthChallenge.Purpose.PASSWORD_RESET,
            member=self.member,
            context_identifier=f"{EmailAuthChallenge.Purpose.PASSWORD_RESET}:{self.member.pk}",
            consume=True,
        )

    def test_phone_only_user_creates_initial_password_via_sms(self, mock_start, mock_check):
        token = self._request_and_verify(mock_start, mock_check)
        mock_check.assert_called_once_with(
            phone_number="+12095551234",
            code="123456",
            challenge_id=None,
            purpose=EmailAuthChallenge.Purpose.PASSWORD_CHANGE,
            member=self.member,
            context_identifier=f"{EmailAuthChallenge.Purpose.PASSWORD_CHANGE}:{self.member.pk}",
            consume=True,
        )

        confirm = self.client.post(
            CONFIRM_URL,
            {"verification_token": token, "new_password": NEW_PASSWORD, "new_password_confirm": NEW_PASSWORD},
            format="json",
        )
        self.assertEqual(confirm.status_code, 200)
        self.member.refresh_from_db()
        self.assertTrue(self.member.check_password(NEW_PASSWORD))

    def test_wrong_otp_does_not_mint_a_token(self, _mock_start, mock_check):
        self.client.post(REQUEST_URL, {}, format="json")
        mock_check.return_value = (None, "invalid")
        verify = self.client.post(VERIFY_URL, {"code": "000000"}, format="json")
        self.assertEqual(verify.status_code, 400)
        self.assertFalse(
            EmailAuthChallenge.objects.filter(
                member=self.member,
                purpose=EmailAuthChallenge.Purpose.PASSWORD_CHANGE,
                status=EmailAuthChallenge.Status.VERIFIED,
            ).exists()
        )

    def test_over_attempted_otp_is_rejected(self, _mock_start, mock_check):
        self.client.post(REQUEST_URL, {}, format="json")
        mock_check.return_value = (None, "throttled")
        verify = self.client.post(VERIFY_URL, {"code": "000000"}, format="json")
        self.assertEqual(verify.status_code, 400)
