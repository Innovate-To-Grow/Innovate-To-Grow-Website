from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APITestCase

from authn.models import ContactEmail, EmailAuthChallenge

Member = get_user_model()


@patch("authn.services.email.send_email.send_verification_email")
@patch("authn.services.email_challenges._random_code", return_value="654321")
class EmailCodeAuthLoginTests(APITestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.password = "StrongPass123!"
        self.member = Member.objects.create_user(
            username="member",
            email="",
            password=self.password,
            is_active=True,
        )
        self.primary_email = ContactEmail.objects.create(
            member=self.member,
            email_address="member@example.com",
            email_type="primary",
            verified=True,
        )
        self.alias = ContactEmail.objects.create(
            member=self.member,
            email_address="alias@example.com",
            verified=True,
        )

    def test_password_login_accepts_verified_contact_email(self, _mock_code, _mock_send):
        response = self.client.post(
            "/authn/login/",
            {"email": self.alias.email_address, "password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user"]["email"], self.primary_email.email_address)
        self.assertIn("access", response.data)

    def test_password_login_rejects_unverified_contact_email(self, _mock_code, _mock_send):
        unverified = ContactEmail.objects.create(
            member=self.member,
            email_address="pending@example.com",
            verified=False,
        )

        response = self.client.post(
            "/authn/login/",
            {"email": unverified.email_address, "password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["non_field_errors"][0], "Invalid credentials.")

    def test_login_code_flow_accepts_verified_contact_email(self, _mock_code, mock_send):
        request_response = self.client.post(
            "/authn/login/request-code/",
            {"email": self.alias.email_address},
            format="json",
        )

        self.assertEqual(request_response.status_code, 202)
        self.assertEqual(EmailAuthChallenge.objects.count(), 1)
        mock_send.assert_called_once()

        verify_response = self.client.post(
            "/authn/login/verify-code/",
            {"email": self.alias.email_address, "code": "654321"},
            format="json",
        )

        self.assertEqual(verify_response.status_code, 200)
        self.assertEqual(verify_response.data["user"]["email"], self.primary_email.email_address)
        self.assertEqual(EmailAuthChallenge.objects.first().status, EmailAuthChallenge.Status.CONSUMED)

    def test_unified_email_auth_uses_login_flow_for_active_primary_email(self, _mock_code, _mock_send):
        request_response = self.client.post(
            "/authn/email-auth/request-code/",
            {"email": self.primary_email.email_address},
            format="json",
        )

        self.assertEqual(request_response.status_code, 202)
        self.assertEqual(request_response.data["flow"], "login")
        self.assertEqual(request_response.data["next_step"], "verify_code")

        verify_response = self.client.post(
            "/authn/email-auth/verify-code/",
            {"email": self.primary_email.email_address, "code": "654321"},
            format="json",
        )

        self.assertEqual(verify_response.status_code, 200)
        self.assertEqual(verify_response.data["next_step"], "account")
        self.assertFalse(verify_response.data["requires_profile_completion"])
        self.assertIn("access", verify_response.data)

    def test_unified_email_auth_uses_login_flow_for_verified_contact_email(self, _mock_code, _mock_send):
        request_response = self.client.post(
            "/authn/email-auth/request-code/",
            {"email": self.alias.email_address},
            format="json",
        )

        self.assertEqual(request_response.status_code, 202)
        self.assertEqual(request_response.data["flow"], "login")

        verify_response = self.client.post(
            "/authn/email-auth/verify-code/",
            {"email": self.alias.email_address, "code": "654321"},
            format="json",
        )

        self.assertEqual(verify_response.status_code, 200)
        self.assertEqual(verify_response.data["user"]["email"], self.primary_email.email_address)
        self.assertEqual(verify_response.data["next_step"], "account")
        self.assertFalse(verify_response.data["requires_profile_completion"])

    def test_unified_email_auth_creates_pending_member_without_password(self, _mock_code, _mock_send):
        request_response = self.client.post(
            "/authn/email-auth/request-code/",
            {"email": "new-flow@example.com"},
            format="json",
        )

        self.assertEqual(request_response.status_code, 202)
        self.assertEqual(request_response.data["flow"], "register")
        pending = ContactEmail.objects.get(email_address="new-flow@example.com").member
        self.assertFalse(pending.is_active)
        self.assertFalse(pending.has_usable_password())
        self.assertEqual(pending.first_name, "")
        self.assertEqual(pending.organization, "")

        verify_response = self.client.post(
            "/authn/email-auth/verify-code/",
            {"email": "new-flow@example.com", "code": "654321"},
            format="json",
        )

        pending.refresh_from_db()
        self.assertEqual(verify_response.status_code, 200)
        self.assertTrue(pending.is_active)
        self.assertEqual(verify_response.data["next_step"], "complete_profile")
        self.assertTrue(verify_response.data["requires_profile_completion"])
        self.assertIn("access", verify_response.data)

    def test_unified_email_auth_reuses_pending_member(self, _mock_code, _mock_send):
        pending = Member.objects.create_user(
            username="pending-email-auth",
            email="",
            password="OldPass123!",
            is_active=False,
            first_name="Existing",
        )
        ContactEmail.objects.create(
            member=pending, email_address="pending-flow@example.com", email_type="primary", verified=True
        )

        request_response = self.client.post(
            "/authn/email-auth/request-code/",
            {"email": "pending-flow@example.com"},
            format="json",
        )

        pending.refresh_from_db()
        self.assertEqual(request_response.status_code, 202)
        self.assertEqual(request_response.data["flow"], "register")
        self.assertEqual(ContactEmail.objects.filter(email_address="pending-flow@example.com").count(), 1)
        self.assertEqual(pending.first_name, "Existing")

    def test_unified_email_auth_rejects_conflicting_contact_email(self, _mock_code, _mock_send):
        ContactEmail.objects.create(
            member=self.member,
            email_address="blocked@example.com",
            verified=False,
        )

        response = self.client.post(
            "/authn/email-auth/request-code/",
            {"email": "blocked@example.com"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["email"], "This email cannot be used for registration.")
        self.assertEqual(EmailAuthChallenge.objects.count(), 0)
