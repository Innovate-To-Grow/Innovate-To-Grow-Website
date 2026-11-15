"""Tests for ImpersonateLoginView — one-time-use token flow."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.authn.models import ContactEmail, ImpersonationToken
from apps.authn.tests.helpers import (
    MALFORMED_TOKEN_BODIES,
    UNUSABLE_TOKEN_BODIES,
    access_token_owner_id,
    bearer_header,
    stale_bearer_headers,
)

Member = get_user_model()
URL = "/authn/impersonate-login/"


class ImpersonateLoginTests(APITestCase):
    # noinspection PyPep8Naming,PyAttributeOutsideInit
    def setUp(self):
        cache.clear()
        self.admin = Member.objects.create_superuser(
            password="AdminPass123!",
            first_name="Admin",
            last_name="User",
        )
        ContactEmail.objects.create(
            member=self.admin, email_address="admin@example.com", email_type="primary", verified=True
        )
        self.target = Member.objects.create_user(password="TargetPass123!", is_active=True)
        ContactEmail.objects.create(
            member=self.target, email_address="target@example.com", email_type="primary", verified=True
        )

    def _make_token(self, **kwargs):
        defaults = {"member": self.target, "created_by": self.admin, "token": ImpersonationToken.generate_token()}
        defaults.update(kwargs)
        return ImpersonationToken.objects.create(**defaults)

    def test_valid_token_returns_jwt_for_impersonated_member(self):
        token = self._make_token()
        response = self.client.post("/authn/impersonate-login/", {"token": token.token}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(response.data["next_step"], "complete_profile")
        self.assertTrue(response.data["requires_profile_completion"])
        token.refresh_from_db()
        self.assertTrue(token.is_used)

    def test_incomplete_profile_routes_to_complete_profile(self):
        self.target.first_name = ""
        self.target.last_name = ""
        self.target.save(update_fields=["first_name", "last_name", "updated_at"])
        token = self._make_token()

        response = self.client.post("/authn/impersonate-login/", {"token": token.token}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["next_step"], "complete_profile")
        self.assertTrue(response.data["requires_profile_completion"])

    def test_missing_token_returns_400(self):
        response = self.client.post("/authn/impersonate-login/", {}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_unknown_token_returns_400(self):
        response = self.client.post("/authn/impersonate-login/", {"token": "nope"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_already_used_token_returns_400(self):
        token = self._make_token()
        first = self.client.post("/authn/impersonate-login/", {"token": token.token}, format="json")
        self.assertEqual(first.status_code, 200)

        second = self.client.post("/authn/impersonate-login/", {"token": token.token}, format="json")
        self.assertEqual(second.status_code, 400)
        self.assertIn("already been used", second.data["detail"])

    def test_expired_token_returns_400(self):
        token = self._make_token(expires_at=timezone.now() - timedelta(minutes=1))
        response = self.client.post("/authn/impersonate-login/", {"token": token.token}, format="json")
        self.assertEqual(response.status_code, 400)
        token.refresh_from_db()
        self.assertFalse(token.is_used)

    def test_stale_bearer_does_not_block_the_exchange(self):
        """The token is authenticated by the body; a dead session's Bearer must not 401 it first."""
        for label, header in stale_bearer_headers().items():
            with self.subTest(bearer=label):
                token = self._make_token()

                response = self.client.post(URL, {"token": token.token}, format="json", HTTP_AUTHORIZATION=header)

                self.assertEqual(response.status_code, 200)
                self.assertEqual(access_token_owner_id(response.data["access"]), str(self.target.pk))
                token.refresh_from_db()
                self.assertTrue(token.is_used)

    def test_bearer_of_another_member_logs_in_as_the_token_owner(self):
        """An admin already signed in on this browser must still become the impersonated member."""
        token = self._make_token()

        response = self.client.post(
            URL, {"token": token.token}, format="json", HTTP_AUTHORIZATION=bearer_header(self.admin)
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(access_token_owner_id(response.data["access"]), str(self.target.pk))
        token.refresh_from_db()
        self.assertTrue(token.is_used)

    def test_malformed_token_bodies_return_400(self):
        for label, body in MALFORMED_TOKEN_BODIES.items():
            with self.subTest(body=label):
                response = self.client.post(URL, body, content_type="application/json")

                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.data["detail"], "Token is required.")

    def test_unusable_token_strings_return_400_before_reaching_the_database(self):
        """A lone surrogate is a 500 in the SQLite driver and NUL is one on PostgreSQL; neither is ever looked up."""
        for label, body in UNUSABLE_TOKEN_BODIES.items():
            with self.subTest(body=label):
                response = self.client.post(URL, body, content_type="application/json")

                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.data["detail"], "Token is required.")
