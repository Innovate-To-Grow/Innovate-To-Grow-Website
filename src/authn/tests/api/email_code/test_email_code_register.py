from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APITestCase

from authn.models import ContactEmail

Member = get_user_model()


@patch("authn.services.email.send_email.send_verification_email")
@patch("authn.services.email_challenges._random_code", return_value="654321")
class EmailCodeAuthRegisterTests(APITestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.password = "StrongPass123!"
        self.member = Member.objects.create_user(
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

    def test_register_creates_inactive_member_then_activates_on_verify(self, _mock_code, _mock_send):
        response = self.client.post(
            "/authn/register/",
            {
                "email": "new-member@example.com",
                "password": self.password,
                "password_confirm": self.password,
                "first_name": "New",
                "last_name": "Member",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 202)
        member = ContactEmail.objects.get(email_address="new-member@example.com").member
        self.assertFalse(member.is_active)

        verify_response = self.client.post(
            "/authn/register/verify-code/",
            {"email": "new-member@example.com", "code": "654321"},
            format="json",
        )

        member.refresh_from_db()
        self.assertEqual(verify_response.status_code, 200)
        self.assertTrue(member.is_active)
        self.assertIn("access", verify_response.data)

    def test_register_reuses_pending_member(self, _mock_code, _mock_send):
        pending = Member.objects.create_user(
            password="OldPass123!",
            is_active=False,
            first_name="Old",
        )
        ContactEmail.objects.create(
            member=pending, email_address="pending@example.com", email_type="primary", verified=True
        )

        response = self.client.post(
            "/authn/register/",
            {
                "email": "pending@example.com",
                "password": self.password,
                "password_confirm": self.password,
                "first_name": "Updated",
                "last_name": "User",
            },
            format="json",
        )

        pending.refresh_from_db()
        self.assertEqual(response.status_code, 202)
        self.assertEqual(ContactEmail.objects.filter(email_address="pending@example.com").count(), 1)
        self.assertEqual(pending.first_name, "Updated")
        self.assertTrue(pending.check_password(self.password))

    def test_register_rejects_existing_contact_email(self, _mock_code, _mock_send):
        response = self.client.post(
            "/authn/register/",
            {
                "email": self.alias.email_address,
                "password": self.password,
                "password_confirm": self.password,
                "first_name": "Alias",
                "last_name": "Conflict",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("already exists", response.data["email"][0])
