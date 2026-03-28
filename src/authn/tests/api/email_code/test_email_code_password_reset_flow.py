from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APITestCase

from authn.models import ContactEmail, EmailAuthChallenge

Member = get_user_model()


class EmailCodePasswordResetFlowTests(APITestCase):
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

    def test_password_reset_flow_works_with_verified_contact_email(self, _mock_code, _mock_send):
        request_response = self.client.post(
            "/authn/password-reset/request-code/",
            {"email": self.alias.email_address},
            format="json",
        )
        self.assertEqual(request_response.status_code, 202)

        verify_response = self.client.post(
            "/authn/password-reset/verify-code/",
            {"email": self.alias.email_address, "code": "333333"},
            format="json",
        )
        self.assertEqual(verify_response.status_code, 200)
        token = verify_response.data["verification_token"]

        confirm_response = self.client.post(
            "/authn/password-reset/confirm/",
            {
                "email": self.alias.email_address,
                "verification_token": token,
                "new_password": "NewStrongPass123!",
                "new_password_confirm": "NewStrongPass123!",
            },
            format="json",
        )

        self.member.refresh_from_db()
        self.assertEqual(confirm_response.status_code, 200)
        self.assertTrue(self.member.check_password("NewStrongPass123!"))

    def test_new_code_invalidates_previous_code(self, _mock_code, _mock_send):
        first_response = self.client.post(
            "/authn/login/request-code/",
            {"email": self.alias.email_address},
            format="json",
        )
        self.assertEqual(first_response.status_code, 202)

        challenge = EmailAuthChallenge.objects.get(target_email=self.alias.email_address)
        challenge.last_sent_at = timezone.now() - timedelta(minutes=2)
        challenge.save(update_fields=["last_sent_at"])

        second_response = self.client.post(
            "/authn/login/request-code/",
            {"email": self.alias.email_address},
            format="json",
        )
        self.assertEqual(second_response.status_code, 202)

        old_code_response = self.client.post(
            "/authn/login/verify-code/",
            {"email": self.alias.email_address, "code": "555555"},
            format="json",
        )
        self.assertEqual(old_code_response.status_code, 400)

        new_code_response = self.client.post(
            "/authn/login/verify-code/",
            {"email": self.alias.email_address, "code": "666666"},
            format="json",
        )
        self.assertEqual(new_code_response.status_code, 200)

    def test_password_reset_request_same_response_for_unknown_email(self, _mock_send):
        """Password reset for non-existent email should not reveal whether the email exists."""
        response = self.client.post(
            "/authn/password-reset/request-code/",
            {"email": "nonexistent@example.com"},
            format="json",
        )
        # Should return a success-like status (not 404) to prevent email enumeration
        self.assertIn(response.status_code, [200, 202])
