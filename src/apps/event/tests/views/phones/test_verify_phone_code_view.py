from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from apps.authn.services.sms import (
    PhoneVerificationInvalid,
    PhoneVerificationThrottled,
)
from apps.event.tests.helpers import load_urlconf, make_event, make_member
from apps.event.views.registration.phones import (
    LEGACY_EVENT_REGISTRATION_CONTEXT,
)


class VerifyPhoneCodeViewTest(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # These tests patch apps.authn.services.sms.check_phone_verification around a request. Import the views first,
        # or apps.authn.views.auth.codes.phone_code could bind the mock for every later phone-auth test in this process (a
        # MagicMock response never finishes rendering: DRF's JSON encoder keeps calling .tolist() on it).
        load_urlconf()

    def setUp(self):
        self.client = APIClient()
        self.member = make_member()
        self.client.force_authenticate(self.member)
        self.event = make_event(registration_open=True, collect_phone=True, verify_phone=True)

    def _payload(self, **values):
        return {"event_slug": self.event.slug, **values}

    def test_missing_phone_or_code_returns_400(self):
        response = self.client.post(
            "/event/verify-phone-code/",
            self._payload(phone="", code=""),
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "Phone and code are required.")

    @patch("apps.authn.services.sms.check_phone_verification", side_effect=PhoneVerificationThrottled("slow down"))
    def test_throttled_returns_429(self, _mock_check):
        response = self.client.post(
            "/event/verify-phone-code/",
            self._payload(phone="+15551234567", code="123456"),
            format="json",
        )
        self.assertEqual(response.status_code, 429)
        self.assertIn("Too many failed attempts", response.data["detail"])

    @patch("apps.authn.services.sms.check_phone_verification", side_effect=PhoneVerificationInvalid("nope"))
    def test_invalid_code_returns_400(self, _mock_check):
        response = self.client.post(
            "/event/verify-phone-code/",
            self._payload(phone="+15551234567", code="000000"),
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "Invalid or expired verification code.")

    @patch("apps.authn.services.sms.check_phone_verification")
    def test_valid_code_marks_verified(self, mock_check):
        challenge_id = "d7fdd0f5-a53e-4edf-a8f7-bb2ad34396a1"
        mock_check.return_value.pk = challenge_id
        response = self.client.post(
            "/event/verify-phone-code/",
            self._payload(
                phone="+15551234567",
                code="123456",
                challenge_id=challenge_id,
            ),
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["verified"])
        self.assertEqual(response.data["phone"], "+15551234567")
        mock_check.assert_called_once_with(
            "+15551234567",
            "123456",
            challenge_id=challenge_id,
            purpose="event_registration",
            member=self.member,
            context_identifier=f"event-registration:{self.event.pk}",
            consume=False,
        )

    @patch("apps.authn.services.sms.check_phone_verification")
    def test_legacy_phone_only_verification_uses_compatibility_context(
        self,
        mock_check,
    ):
        mock_check.return_value.pk = "d7fdd0f5-a53e-4edf-a8f7-bb2ad34396a1"
        response = self.client.post(
            "/event/verify-phone-code/",
            {"phone": "+15551234567", "code": "123456"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        mock_check.assert_called_once_with(
            "+15551234567",
            "123456",
            challenge_id=None,
            purpose="event_registration",
            member=self.member,
            context_identifier=LEGACY_EVENT_REGISTRATION_CONTEXT,
            consume=False,
        )
