from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.authn.services.sms import (
    PhoneVerificationDeliveryError,
    PhoneVerificationInvalid,
    PhoneVerificationThrottled,
)
from apps.event.tests.helpers import make_member


class SendPhoneCodeViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.member = make_member()
        self.client.force_authenticate(self.member)

    def test_missing_phone_returns_400(self):
        response = self.client.post("/event/send-phone-code/", {"phone": "", "region": "1-US"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "Phone number is required.")

    @patch("apps.authn.services.sms.start_phone_verification", side_effect=PhoneVerificationInvalid("bad"))
    def test_invalid_phone_returns_400(self, _mock_start):
        response = self.client.post("/event/send-phone-code/", {"phone": "5551234567", "region": "1-US"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "Invalid phone number.")

    @patch(
        "apps.authn.services.sms.start_phone_verification",
        side_effect=PhoneVerificationDeliveryError("sns down"),
    )
    def test_delivery_error_returns_503(self, _mock_start):
        response = self.client.post("/event/send-phone-code/", {"phone": "5551234567", "region": "1-US"}, format="json")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["detail"], "Failed to send verification code. Please try again later.")

    @patch("apps.authn.services.sms.start_phone_verification", return_value=None)
    def test_success_returns_normalized_phone(self, mock_start):
        response = self.client.post("/event/send-phone-code/", {"phone": "5551234567", "region": "1-US"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["detail"], "Verification code sent.")
        self.assertEqual(response.data["phone"], "+15551234567")
        mock_start.assert_called_once_with("+15551234567")


class SendPhoneCodeThrottleTest(TestCase):
    """Per-actor rate limit bounds SMS toll-fraud: an authenticated caller cannot
    pump unlimited sends by rotating the destination number."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.member = make_member()
        self.client.force_authenticate(self.member)

    def tearDown(self):
        cache.clear()

    @patch("apps.authn.services.sms.start_phone_verification", return_value=None)
    def test_sends_are_throttled_per_user(self, _mock_start):
        # The rate is 5/minute; rotate the destination number each call so the
        # service-level per-number cap can't be what blocks us.
        last_status = None
        for i in range(6):
            response = self.client.post(
                "/event/send-phone-code/",
                {"phone": f"55512340{i:02d}", "region": "1-US"},
                format="json",
            )
            last_status = response.status_code
        # The 6th send in the window is rejected by the per-user throttle.
        self.assertEqual(last_status, 429)


class VerifyPhoneCodeViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.member = make_member()
        self.client.force_authenticate(self.member)

    def test_missing_phone_or_code_returns_400(self):
        response = self.client.post("/event/verify-phone-code/", {"phone": "", "code": ""}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "Phone and code are required.")

    @patch("apps.authn.services.sms.check_phone_verification", side_effect=PhoneVerificationThrottled("slow down"))
    def test_throttled_returns_429(self, _mock_check):
        response = self.client.post(
            "/event/verify-phone-code/",
            {"phone": "+15551234567", "code": "123456"},
            format="json",
        )
        self.assertEqual(response.status_code, 429)
        self.assertIn("Too many failed attempts", response.data["detail"])

    @patch("apps.authn.services.sms.check_phone_verification", side_effect=PhoneVerificationInvalid("nope"))
    def test_invalid_code_returns_400(self, _mock_check):
        response = self.client.post(
            "/event/verify-phone-code/",
            {"phone": "+15551234567", "code": "000000"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "Invalid or expired verification code.")

    @patch("apps.authn.services.sms.check_phone_verification", return_value="approved")
    def test_valid_code_marks_verified(self, _mock_check):
        response = self.client.post(
            "/event/verify-phone-code/",
            {"phone": "+15551234567", "code": "123456"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["verified"])
        self.assertEqual(response.data["phone"], "+15551234567")
