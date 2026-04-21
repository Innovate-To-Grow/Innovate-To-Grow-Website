"""Tests for UnsubscribeAutoLoginView endpoint."""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APITestCase

from authn.models import ContactEmail
from authn.services.unsubscribe_token import build_unsubscribe_login_token

Member = get_user_model()


class UnsubscribeAutoLoginViewTests(APITestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.member = Member.objects.create_user(
            password="StrongPass123!",
            is_active=True,
        )
        ContactEmail.objects.create(
            member=self.member, email_address="unsub@example.com", email_type="primary", verified=True
        )

    def test_valid_token_returns_jwt(self):
        token = build_unsubscribe_login_token(self.member)
        response = self.client.post(
            "/authn/unsubscribe-login/",
            {"token": token},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertIn("user", response.data)
        self.assertEqual(response.data["user"]["email"], "unsub@example.com")
        self.assertEqual(response.data["next_step"], "complete_profile")
        self.assertTrue(response.data["requires_profile_completion"])

    def test_incomplete_profile_routes_to_complete_profile(self):
        self.member.first_name = ""
        self.member.last_name = ""
        self.member.save(update_fields=["first_name", "last_name", "updated_at"])
        token = build_unsubscribe_login_token(self.member)

        response = self.client.post(
            "/authn/unsubscribe-login/",
            {"token": token},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["next_step"], "complete_profile")
        self.assertTrue(response.data["requires_profile_completion"])

    def test_invalid_token_returns_400(self):
        response = self.client.post(
            "/authn/unsubscribe-login/",
            {"token": "garbage-invalid-token"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_missing_token_returns_400(self):
        response = self.client.post(
            "/authn/unsubscribe-login/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_inactive_member_returns_400(self):
        self.member.is_active = False
        self.member.save(update_fields=["is_active"])
        token = build_unsubscribe_login_token(self.member)
        response = self.client.post(
            "/authn/unsubscribe-login/",
            {"token": token},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_token_can_only_be_used_once(self):
        token = build_unsubscribe_login_token(self.member)

        first_response = self.client.post(
            "/authn/unsubscribe-login/",
            {"token": token},
            format="json",
        )
        self.assertEqual(first_response.status_code, 200)

        second_response = self.client.post(
            "/authn/unsubscribe-login/",
            {"token": token},
            format="json",
        )
        self.assertEqual(second_response.status_code, 400)
        self.assertEqual(second_response.data["detail"], "This login link has already been used.")
