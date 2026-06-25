"""Passwordless phone-auth: new-account (register) flow."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APITestCase

from apps.authn.models import ContactPhone

Member = get_user_model()

REQUEST_URL = "/authn/phone-auth/request-code/"
VERIFY_URL = "/authn/phone-auth/verify-code/"


@patch("apps.authn.views.auth.phone_code.check_phone_verification", return_value="approved")
@patch("apps.authn.services.sms.start_phone_verification", return_value="pending")
class PhoneAuthRegisterTests(APITestCase):
    # noinspection PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def test_request_code_new_phone_returns_202_and_sends_e164(self, mock_start, _mock_check):
        response = self.client.post(REQUEST_URL, {"phone_number": "2025550123"}, format="json")
        self.assertEqual(response.status_code, 202)
        self.assertIn("message", response.data)
        mock_start.assert_called_once()
        self.assertEqual(mock_start.call_args.args[0], "+12025550123")

    def test_request_code_normalizes_formatted_input(self, mock_start, _mock_check):
        response = self.client.post(REQUEST_URL, {"phone_number": "+1 (202) 555-0123"}, format="json")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(mock_start.call_args.args[0], "+12025550123")

    def test_verify_new_phone_creates_active_member_and_verified_contact(self, _mock_start, _mock_check):
        response = self.client.post(VERIFY_URL, {"phone_number": "2025550123", "code": "654321"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["message"], "Registration successful.")
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(response.data["next_step"], "complete_profile")
        self.assertTrue(response.data["requires_profile_completion"])
        # Phone-only account: phone present in payload, email empty.
        self.assertEqual(response.data["user"]["phone"], "+12025550123")
        self.assertEqual(response.data["user"]["email"], "")

        contact = ContactPhone.objects.get(phone_number="2025550123")
        self.assertTrue(contact.verified)
        self.assertIsNotNone(contact.member)
        self.assertTrue(contact.member.is_active)
        self.assertTrue(contact.member.requires_profile_completion)
        self.assertFalse(contact.member.has_usable_password())

    def test_verify_claims_orphan_member_less_phone(self, _mock_start, _mock_check):
        ContactPhone.objects.create(member=None, phone_number="2025550123", region="1-US", verified=False)
        response = self.client.post(VERIFY_URL, {"phone_number": "2025550123", "code": "654321"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["message"], "Registration successful.")
        contact = ContactPhone.objects.get(phone_number="2025550123")
        self.assertIsNotNone(contact.member)
        self.assertTrue(contact.verified)
        # No duplicate row was created.
        self.assertEqual(ContactPhone.objects.filter(phone_number="2025550123").count(), 1)
