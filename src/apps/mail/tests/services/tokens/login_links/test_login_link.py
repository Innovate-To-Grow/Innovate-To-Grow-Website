from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from apps.event.tests.helpers import make_member
from apps.mail.models import EmailCampaign, LoginLinkToken
from apps.mail.redirects import DEFAULT_LOGIN_REDIRECT_PATH


class LoginLinkViewTests(APITestCase):
    def setUp(self):
        self.member = make_member(email="magic@example.com")
        self.campaign = EmailCampaign.objects.create(
            subject="Spring Update",
            body="Draft body",
            login_redirect_path="/schedule",
        )

    def test_valid_token_returns_redirect_to_matching_campaign(self):
        token = LoginLinkToken.generate_token()
        LoginLinkToken.objects.create(token=token, member=self.member, campaign=self.campaign)

        response = self.client.post("/mail/login-link/", {"token": token}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(response.data["redirect_to"], "/schedule")
        self.assertEqual(response.data["next_step"], "complete_profile")
        self.assertTrue(response.data["requires_profile_completion"])

    def test_legacy_magic_login_endpoint_still_works(self):
        token = LoginLinkToken.generate_token()
        LoginLinkToken.objects.create(token=token, member=self.member, campaign=self.campaign)

        response = self.client.post("/mail/magic-login/", {"token": token}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["redirect_to"], "/schedule")

    def test_null_campaign_falls_back_to_account_redirect(self):
        token = LoginLinkToken.generate_token()
        LoginLinkToken.objects.create(token=token, member=self.member, campaign=None)

        response = self.client.post("/mail/login-link/", {"token": token}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["redirect_to"], DEFAULT_LOGIN_REDIRECT_PATH)

    def test_token_redirect_path_used_when_no_campaign(self):
        token = LoginLinkToken.generate_token()
        LoginLinkToken.objects.create(
            token=token, member=self.member, campaign=None, redirect_path="/event-registration"
        )

        response = self.client.post("/mail/login-link/", {"token": token}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["redirect_to"], "/event-registration")

    def test_incomplete_profile_routes_to_complete_profile(self):
        self.member.first_name = ""
        self.member.last_name = ""
        self.member.save(update_fields=["first_name", "last_name", "updated_at"])
        token = LoginLinkToken.generate_token()
        LoginLinkToken.objects.create(token=token, member=self.member, campaign=self.campaign)

        response = self.client.post("/mail/login-link/", {"token": token}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["next_step"], "complete_profile")
        self.assertTrue(response.data["requires_profile_completion"])

    def test_token_cannot_be_reused_by_default(self):
        token = LoginLinkToken.generate_token()
        LoginLinkToken.objects.create(token=token, member=self.member, campaign=self.campaign)

        first_response = self.client.post("/mail/login-link/", {"token": token}, format="json")
        self.assertEqual(first_response.status_code, 200)

        second_response = self.client.post("/mail/login-link/", {"token": token}, format="json")
        self.assertEqual(second_response.status_code, 400)
        self.assertEqual(second_response.data["detail"], "This login link has already been used.")

    def test_used_token_records_used_at(self):
        token = LoginLinkToken.generate_token()
        link = LoginLinkToken.objects.create(token=token, member=self.member, campaign=self.campaign)
        self.assertFalse(link.is_used)

        self.client.post("/mail/login-link/", {"token": token}, format="json")

        link.refresh_from_db()
        self.assertTrue(link.is_used)
        self.assertIsNotNone(link.used_at)

    def test_expired_token_still_returns_existing_error(self):
        token = LoginLinkToken.generate_token()
        LoginLinkToken.objects.create(
            token=token,
            member=self.member,
            campaign=self.campaign,
            expires_at=timezone.now() - timedelta(seconds=1),
        )

        response = self.client.post("/mail/login-link/", {"token": token}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "This login link has expired.")

    def test_inactive_member_is_rejected_with_generic_error(self):
        # The old ticket-login flow enforced is_active; the unified endpoint must too.
        self.member.is_active = False
        self.member.save(update_fields=["is_active", "updated_at"])
        token = LoginLinkToken.generate_token()
        LoginLinkToken.objects.create(token=token, member=self.member, campaign=self.campaign)

        response = self.client.post("/mail/login-link/", {"token": token}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "Invalid login link.")
