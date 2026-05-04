from datetime import timedelta
from unittest.mock import patch

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
        self.assertEqual(response.data["next_step"], "complete_profile")
        self.assertTrue(response.data["requires_profile_completion"])

    def test_null_campaign_falls_back_to_account_redirect(self):
        token = MagicLoginToken.generate_token()
        MagicLoginToken.objects.create(token=token, member=self.member, campaign=None)

        response = self.client.post("/mail/magic-login/", {"token": token}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["redirect_to"], DEFAULT_LOGIN_REDIRECT_PATH)

    def test_incomplete_profile_routes_to_complete_profile(self):
        self.member.first_name = ""
        self.member.last_name = ""
        self.member.save(update_fields=["first_name", "last_name", "updated_at"])
        token = MagicLoginToken.generate_token()
        MagicLoginToken.objects.create(token=token, member=self.member, campaign=self.campaign)

        response = self.client.post("/mail/magic-login/", {"token": token}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["next_step"], "complete_profile")
        self.assertTrue(response.data["requires_profile_completion"])

    def test_token_can_be_reused(self):
        token = MagicLoginToken.generate_token()
        MagicLoginToken.objects.create(token=token, member=self.member, campaign=self.campaign)

        first_response = self.client.post("/mail/magic-login/", {"token": token}, format="json")
        self.assertEqual(first_response.status_code, 200)

        second_response = self.client.post("/mail/magic-login/", {"token": token}, format="json")
        self.assertEqual(second_response.status_code, 200)
        self.assertIn("access", second_response.data)

    def test_used_token_records_used_at(self):
        token = MagicLoginToken.generate_token()
        magic = MagicLoginToken.objects.create(token=token, member=self.member, campaign=self.campaign)
        self.assertFalse(magic.is_used)

        self.client.post("/mail/magic-login/", {"token": token}, format="json")

        magic.refresh_from_db()
        self.assertTrue(magic.is_used)
        self.assertIsNotNone(magic.used_at)

    def test_reuse_updates_used_at(self):
        token = MagicLoginToken.generate_token()
        magic = MagicLoginToken.objects.create(token=token, member=self.member, campaign=self.campaign)

        self.client.post("/mail/magic-login/", {"token": token}, format="json")
        magic.refresh_from_db()
        first_used_at = magic.used_at

        self.client.post("/mail/magic-login/", {"token": token}, format="json")
        magic.refresh_from_db()
        self.assertGreaterEqual(magic.used_at, first_used_at)

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


class MagicLoginTokenRecordUseTests(APITestCase):
    """The ``record_use`` method should update ``is_used`` and ``used_at``
    on every call, allowing the same token to be used multiple times."""

    def setUp(self):
        self.member = make_member(email="race@example.com")
        self.campaign = EmailCampaign.objects.create(subject="s", body="b")

    def test_record_use_sets_is_used_and_used_at(self):
        token = MagicLoginToken.generate_token()
        magic = MagicLoginToken.objects.create(token=token, member=self.member, campaign=self.campaign)

        self.assertFalse(magic.is_used)
        magic.record_use()
        magic.refresh_from_db()
        self.assertTrue(magic.is_used)
        self.assertIsNotNone(magic.used_at)

    def test_record_use_updates_used_at_on_repeated_calls(self):
        token = MagicLoginToken.generate_token()
        magic = MagicLoginToken.objects.create(token=token, member=self.member, campaign=self.campaign)

        magic.record_use()
        first_used_at = magic.used_at

        magic.record_use()
        self.assertGreaterEqual(magic.used_at, first_used_at)

    @patch("mail.views.MagicLoginView.throttle_classes", [])
    def test_multiple_login_requests_all_succeed(self):
        token = MagicLoginToken.generate_token()
        MagicLoginToken.objects.create(token=token, member=self.member, campaign=self.campaign)

        first = self.client.post("/mail/magic-login/", {"token": token}, format="json")
        second = self.client.post("/mail/magic-login/", {"token": token}, format="json")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
