from unittest.mock import patch

from django.core.cache import cache
from rest_framework.test import APITestCase

from apps.authn.models import ContactEmail
from apps.authn.services import AuthChallengeDeliveryError, AuthChallengeInvalid
from apps.authn.tests.api.account.contact_emails.test_contact_emails_edge import Member


class AccountEmailCodeViewEdgeTests(APITestCase):
    """Covers the authenticated change-password / delete-account code views."""

    def setUp(self):
        cache.clear()
        self.member = Member.objects.create_user(password="StrongPass123!", is_active=True)
        ContactEmail.objects.create(
            member=self.member, email_address="user@example.com", email_type="primary", verified=True
        )
        self.client.force_authenticate(user=self.member)

    @patch("apps.authn.services.email.send_email.send_verification_email")
    def test_change_password_request_without_email_selects_verified_email(self, _mock_send):
        # An empty payload is now valid: the backend auto-selects the verification
        # channel (the member's verified email here), mirroring the phone-only SMS path.
        resp = self.client.post("/authn/change-password/request-code/", {}, format="json")
        self.assertEqual(resp.status_code, 202)
        self.assertEqual(resp.data["channel"], "email")

    def test_change_password_request_without_recovery_contact_returns_400(self):
        # A member with no verified email or phone has no channel to verify through.
        member = Member.objects.create_user(password="StrongPass123!", is_active=True)
        self.client.force_authenticate(user=member)
        resp = self.client.post("/authn/change-password/request-code/", {}, format="json")
        self.assertEqual(resp.status_code, 400)

    @patch("apps.authn.serializers.email_code.password_change.ChangePasswordCodeRequestSerializer.save")
    def test_change_password_request_delivery_error_returns_503(self, mock_save):
        mock_save.side_effect = AuthChallengeDeliveryError("ses rejected", outcome="permanent")
        resp = self.client.post(
            "/authn/change-password/request-code/",
            {"email": "user@example.com"},
            format="json",
        )
        self.assertEqual(resp.status_code, 503)

    def test_change_password_verify_invalid_payload(self):
        resp = self.client.post("/authn/change-password/verify-code/", {}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_change_password_confirm_invalid_payload(self):
        resp = self.client.post("/authn/change-password/confirm/", {}, format="json")
        self.assertEqual(resp.status_code, 400)

    @patch("apps.authn.serializers.email_code.password_change.ChangePasswordCodeConfirmSerializer.save")
    def test_change_password_confirm_auth_invalid_returns_400(self, mock_save):
        mock_save.side_effect = AuthChallengeInvalid("expired")
        resp = self.client.post(
            "/authn/change-password/confirm/",
            {
                "verification_token": "tok",
                "new_password": "BrandNewPass123!",
                "new_password_confirm": "BrandNewPass123!",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_delete_account_verify_invalid_payload(self):
        resp = self.client.post("/authn/delete-account/verify-code/", {}, format="json")
        self.assertEqual(resp.status_code, 400)

    @patch("apps.authn.serializers.email_code.account_deletion.DeleteAccountCodeRequestSerializer.save")
    def test_delete_account_request_delivery_error_returns_503(self, mock_save):
        mock_save.side_effect = AuthChallengeDeliveryError("ses rejected", outcome="permanent")
        resp = self.client.post("/authn/delete-account/request-code/", {}, format="json")
        self.assertEqual(resp.status_code, 503)

    def test_delete_account_verify_invalid_code_format_returns_400(self):
        resp = self.client.post("/authn/delete-account/verify-code/", {"code": "abcdef"}, format="json")
        self.assertEqual(resp.status_code, 400)
