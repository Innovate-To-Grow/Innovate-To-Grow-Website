from unittest.mock import patch

from apps.authn.models import ContactPhone
from apps.authn.services import (
    PhoneVerificationDeliveryError,
    PhoneVerificationInvalid,
    PhoneVerificationThrottled,
)
from apps.authn.services.email.challenges import AuthChallengeInvalid
from apps.authn.tests.api.account.contact_phones.test_contact_phones import _ContactPhoneCase


class ContactPhoneTests(_ContactPhoneCase):
    def test_cannot_patch_other_users_phone(self):
        phone = ContactPhone.objects.create(member=self.other_member, phone_number="2025551234", region="1-US")
        response = self.client.patch(
            f"/authn/contact-phones/{phone.pk}/",
            {"subscribe": True},
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_delete_returns_204(self):
        phone = ContactPhone.objects.create(member=self.member, phone_number="2025551234", region="1-US")
        response = self.client.delete(f"/authn/contact-phones/{phone.pk}/")
        self.assertEqual(response.status_code, 204)

        # Soft-deleted: not visible via objects
        self.assertFalse(ContactPhone.objects.filter(pk=phone.pk).exists())

    def test_cannot_delete_other_users_phone(self):
        phone = ContactPhone.objects.create(member=self.other_member, phone_number="2025551234", region="1-US")
        response = self.client.delete(f"/authn/contact-phones/{phone.pk}/")
        self.assertEqual(response.status_code, 404)

    def test_patch_invalid_payload_returns_400(self):
        phone = ContactPhone.objects.create(member=self.member, phone_number="2025551234", region="1-US")
        response = self.client.patch(
            f"/authn/contact-phones/{phone.pk}/",
            {"subscribe": "not-a-bool-value-xyz"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    @patch("apps.authn.views.account.contact_phones.request_phone_verification")
    def test_request_verification_success(self, mock_request):
        mock_request.return_value = {"message": "Verification code sent via SMS."}
        phone = ContactPhone.objects.create(member=self.member, phone_number="2025551234", region="1-US")
        response = self.client.post(f"/authn/contact-phones/{phone.pk}/request-verification/")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["message"], "Verification code sent via SMS.")

    @patch("apps.authn.views.account.contact_phones.request_phone_verification")
    def test_request_verification_is_rate_limited_per_user(self, mock_request):
        # An authenticated caller cannot pump unlimited SMS (real SNS spend): the
        # per-user throttle (5/minute) fires regardless of destination rotation.
        from django.core.cache import cache

        cache.clear()
        self.addCleanup(cache.clear)
        mock_request.return_value = {"message": "sent"}
        phone = ContactPhone.objects.create(member=self.member, phone_number="2025551234", region="1-US")
        statuses = [
            self.client.post(f"/authn/contact-phones/{phone.pk}/request-verification/").status_code for _ in range(6)
        ]
        self.assertEqual(statuses[-1], 429)

    @patch("apps.authn.views.account.contact_phones.request_phone_verification")
    def test_request_verification_not_found_returns_400(self, mock_request):
        mock_request.side_effect = AuthChallengeInvalid("nope")
        phone = ContactPhone.objects.create(member=self.member, phone_number="2025551234", region="1-US")
        response = self.client.post(f"/authn/contact-phones/{phone.pk}/request-verification/")
        self.assertEqual(response.status_code, 400)

    @patch("apps.authn.views.account.contact_phones.request_phone_verification")
    def test_request_verification_throttled_returns_429(self, mock_request):
        mock_request.side_effect = PhoneVerificationThrottled()
        phone = ContactPhone.objects.create(member=self.member, phone_number="2025551234", region="1-US")
        response = self.client.post(f"/authn/contact-phones/{phone.pk}/request-verification/")
        self.assertEqual(response.status_code, 429)

    @patch("apps.authn.views.account.contact_phones.request_phone_verification")
    def test_request_verification_delivery_error_returns_503(self, mock_request):
        mock_request.side_effect = PhoneVerificationDeliveryError(outcome="permanent")
        phone = ContactPhone.objects.create(member=self.member, phone_number="2025551234", region="1-US")
        response = self.client.post(f"/authn/contact-phones/{phone.pk}/request-verification/")
        self.assertEqual(response.status_code, 503)

    def test_verify_code_invalid_payload_returns_400(self):
        phone = ContactPhone.objects.create(member=self.member, phone_number="2025551234", region="1-US")
        response = self.client.post(
            f"/authn/contact-phones/{phone.pk}/verify-code/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    @patch("apps.authn.views.account.contact_phones.verify_phone_code")
    def test_verify_code_success(self, mock_verify):
        phone = ContactPhone.objects.create(member=self.member, phone_number="2025551234", region="1-US")
        phone.verified = True
        mock_verify.return_value = phone
        response = self.client.post(
            f"/authn/contact-phones/{phone.pk}/verify-code/",
            {"code": "123456"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["verified"])

    @patch("apps.authn.views.account.contact_phones.verify_phone_code")
    def test_verify_code_auth_challenge_invalid_returns_400(self, mock_verify):
        mock_verify.side_effect = AuthChallengeInvalid("nope")
        phone = ContactPhone.objects.create(member=self.member, phone_number="2025551234", region="1-US")
        response = self.client.post(
            f"/authn/contact-phones/{phone.pk}/verify-code/",
            {"code": "123456"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    @patch("apps.authn.views.account.contact_phones.verify_phone_code")
    def test_verify_code_phone_verification_invalid_returns_400(self, mock_verify):
        mock_verify.side_effect = PhoneVerificationInvalid()
        phone = ContactPhone.objects.create(member=self.member, phone_number="2025551234", region="1-US")
        response = self.client.post(
            f"/authn/contact-phones/{phone.pk}/verify-code/",
            {"code": "123456"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    @patch("apps.authn.views.account.contact_phones.verify_phone_code")
    def test_verify_code_throttled_returns_429(self, mock_verify):
        mock_verify.side_effect = PhoneVerificationThrottled()
        phone = ContactPhone.objects.create(member=self.member, phone_number="2025551234", region="1-US")
        response = self.client.post(
            f"/authn/contact-phones/{phone.pk}/verify-code/",
            {"code": "123456"},
            format="json",
        )
        self.assertEqual(response.status_code, 429)

    def test_unauthenticated_list_rejected(self):
        self.client.force_authenticate(user=None)
        response = self.client.get("/authn/contact-phones/")
        self.assertEqual(response.status_code, 401)
