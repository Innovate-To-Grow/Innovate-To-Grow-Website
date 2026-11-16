from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APITestCase

from apps.authn.models import ContactEmail, EmailAuthChallenge

Member = get_user_model()


class _EmailCodeAuthLoginCase(APITestCase):
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
            email_type="secondary",
            verified=True,
        )


@patch("apps.authn.services.email.send_email.send_verification_email")
@patch("apps.authn.services.email.challenges._random_code", return_value="654321")
class EmailCodeAuthLoginTests(_EmailCodeAuthLoginCase):
    def test_password_login_accepts_verified_contact_email(self, _mock_code, _mock_send):
        response = self.client.post(
            "/authn/login/",
            {"email": self.alias.email_address, "password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user"]["email"], self.primary_email.email_address)
        self.assertNotIn("username", response.data["user"])
        self.assertIn("access", response.data)
        self.assertEqual(response.data["next_step"], "complete_profile")
        self.assertTrue(response.data["requires_profile_completion"])

    def test_password_login_rejects_unverified_contact_email(self, _mock_code, _mock_send):
        unverified = ContactEmail.objects.create(
            member=self.member,
            email_address="pending@example.com",
            email_type="other",
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
        self.assertEqual(mock_send.call_args.kwargs["link_flow"], "login")
        self.assertEqual(mock_send.call_args.kwargs["link_source"], "login")

        verify_response = self.client.post(
            "/authn/login/verify-code/",
            {"email": self.alias.email_address, "code": "654321"},
            format="json",
        )

        self.assertEqual(verify_response.status_code, 200)
        self.assertEqual(verify_response.data["user"]["email"], self.primary_email.email_address)
        self.assertEqual(EmailAuthChallenge.objects.first().status, EmailAuthChallenge.Status.CONSUMED)
        self.assertEqual(verify_response.data["next_step"], "complete_profile")
        self.assertTrue(verify_response.data["requires_profile_completion"])

    def test_password_login_routes_incomplete_profile_to_complete_profile(self, _mock_code, _mock_send):
        self.member.first_name = ""
        self.member.last_name = ""
        self.member.save(update_fields=["first_name", "last_name", "updated_at"])

        response = self.client.post(
            "/authn/login/",
            {"email": self.alias.email_address, "password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["next_step"], "complete_profile")
        self.assertTrue(response.data["requires_profile_completion"])

    def test_login_code_flow_routes_incomplete_profile_to_complete_profile(self, _mock_code, _mock_send):
        self.member.first_name = ""
        self.member.last_name = ""
        self.member.save(update_fields=["first_name", "last_name", "updated_at"])

        self.client.post(
            "/authn/login/request-code/",
            {"email": self.alias.email_address},
            format="json",
        )

        verify_response = self.client.post(
            "/authn/login/verify-code/",
            {"email": self.alias.email_address, "code": "654321"},
            format="json",
        )

        self.assertEqual(verify_response.status_code, 200)
        self.assertEqual(verify_response.data["next_step"], "complete_profile")
        self.assertTrue(verify_response.data["requires_profile_completion"])

    def test_unified_email_auth_uses_login_flow_for_active_primary_email(self, _mock_code, mock_send):
        request_response = self.client.post(
            "/authn/email-auth/request-code/",
            {"email": self.primary_email.email_address},
            format="json",
        )

        self.assertEqual(request_response.status_code, 202)
        self.assertNotIn("flow", request_response.data)
        self.assertNotIn("next_step", request_response.data)
        self.assertEqual(mock_send.call_args.kwargs["link_flow"], "auth")
        self.assertEqual(mock_send.call_args.kwargs["link_source"], "login")

        verify_response = self.client.post(
            "/authn/email-auth/verify-code/",
            {"email": self.primary_email.email_address, "code": "654321"},
            format="json",
        )

        self.assertEqual(verify_response.status_code, 200)
        self.assertEqual(verify_response.data["next_step"], "complete_profile")
        self.assertTrue(verify_response.data["requires_profile_completion"])
        self.assertIn("access", verify_response.data)

    def test_unified_email_auth_uses_requested_source_for_email_link(self, _mock_code, mock_send):
        response = self.client.post(
            "/authn/email-auth/request-code/",
            {"email": self.primary_email.email_address, "source": "subscribe"},
            format="json",
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(mock_send.call_args.kwargs["link_flow"], "auth")
        self.assertEqual(mock_send.call_args.kwargs["link_source"], "subscribe")

    def test_unified_email_auth_forwards_event_slug_to_email_link(self, _mock_code, mock_send):
        response = self.client.post(
            "/authn/email-auth/request-code/",
            {"email": self.primary_email.email_address, "source": "event_registration", "event": "demo-day"},
            format="json",
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(mock_send.call_args.kwargs["link_event"], "demo-day")
