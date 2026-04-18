from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from event.tests.helpers import make_member
from mail.login_redirects import DEFAULT_LOGIN_REDIRECT_PATH
from mail.models import EmailCampaign, MagicLoginToken


class MagicLoginViewTests(APITestCase):
    def setUp(self):
        self.member = make_member(email="magic@example.com")
        self.campaign = EmailCampaign.objects.create(
            subject="Spring Update",
            body="Draft body",
            login_redirect_path="/schedule",
        )

    def test_valid_token_returns_redirect_to_matching_campaign(self):
        token = MagicLoginToken.generate_token()
        MagicLoginToken.objects.create(token=token, member=self.member, campaign=self.campaign)

        response = self.client.post("/mail/magic-login/", {"token": token}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(response.data["redirect_to"], "/schedule")

    def test_null_campaign_falls_back_to_account_redirect(self):
        token = MagicLoginToken.generate_token()
        MagicLoginToken.objects.create(token=token, member=self.member, campaign=None)

        response = self.client.post("/mail/magic-login/", {"token": token}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["redirect_to"], DEFAULT_LOGIN_REDIRECT_PATH)

    def test_reused_token_rejected(self):
        token = MagicLoginToken.generate_token()
        MagicLoginToken.objects.create(token=token, member=self.member, campaign=self.campaign)

        first_response = self.client.post("/mail/magic-login/", {"token": token}, format="json")
        self.assertEqual(first_response.status_code, 200)

        second_response = self.client.post("/mail/magic-login/", {"token": token}, format="json")
        self.assertEqual(second_response.status_code, 400)
        self.assertEqual(second_response.data["detail"], "This login link has already been used.")

    def test_used_token_records_used_at(self):
        token = MagicLoginToken.generate_token()
        magic = MagicLoginToken.objects.create(token=token, member=self.member, campaign=self.campaign)
        self.assertFalse(magic.is_used)

        self.client.post("/mail/magic-login/", {"token": token}, format="json")

        magic.refresh_from_db()
        self.assertTrue(magic.is_used)
        self.assertIsNotNone(magic.used_at)

    def test_expired_token_still_returns_existing_error(self):
        token = MagicLoginToken.generate_token()
        MagicLoginToken.objects.create(
            token=token,
            member=self.member,
            campaign=self.campaign,
            expires_at=timezone.now() - timedelta(seconds=1),
        )

        response = self.client.post("/mail/magic-login/", {"token": token}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "This login link has expired.")
