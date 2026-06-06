from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone
from rest_framework.test import APITestCase

from apps.event.tests.helpers import make_member
from apps.mail.models import EmailCampaign, MagicLoginToken
from apps.mail.utils.redirects import DEFAULT_LOGIN_REDIRECT_PATH


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

    def test_token_cannot_be_reused(self):
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


class MagicLoginTokenConsumptionTests(APITestCase):
    """Magic login tokens must be consumed at most once."""

    def setUp(self):
        self.member = make_member(email="race@example.com")
        self.campaign = EmailCampaign.objects.create(subject="s", body="b")

    def test_try_mark_used_sets_is_used_and_used_at(self):
        token = MagicLoginToken.generate_token()
        magic = MagicLoginToken.objects.create(token=token, member=self.member, campaign=self.campaign)

        self.assertTrue(magic.try_mark_used())
        magic.refresh_from_db()
        self.assertTrue(magic.is_used)
        self.assertIsNotNone(magic.used_at)

    @patch("apps.mail.views.MagicLoginView.throttle_classes", [])
    def test_second_login_request_is_rejected(self):
        token = MagicLoginToken.generate_token()
        MagicLoginToken.objects.create(token=token, member=self.member, campaign=self.campaign)

        first = self.client.post("/mail/magic-login/", {"token": token}, format="json")
        second = self.client.post("/mail/magic-login/", {"token": token}, format="json")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 400)
        self.assertEqual(second.data["detail"], "This login link has already been used.")


class MagicLoginViewErrorTests(APITestCase):
    def setUp(self):
        self.member = make_member(email="err@example.com")

    @patch("apps.mail.views.MagicLoginView.throttle_classes", [])
    def test_missing_token_returns_400(self):
        response = self.client.post("/mail/magic-login/", {"token": "  "}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "Token is required.")

    @patch("apps.mail.views.MagicLoginView.throttle_classes", [])
    def test_unknown_token_returns_400(self):
        response = self.client.post("/mail/magic-login/", {"token": "does-not-exist"}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "Invalid login link.")


class MagicLoginTokenModelTests(APITestCase):
    def setUp(self):
        self.member = make_member(email="model@example.com")

    def test_str_active_and_expired(self):
        active = MagicLoginToken(token="t1", member=self.member)
        expired = MagicLoginToken(token="t2", member=self.member, expires_at=timezone.now() - timedelta(seconds=1))

        self.assertIn("active", str(active))
        self.assertIn("expired", str(expired))

    def test_is_valid_true_for_fresh_token(self):
        token = MagicLoginToken.objects.create(token="fresh", member=self.member)
        self.assertTrue(token.is_valid)

    def test_is_valid_false_when_used(self):
        token = MagicLoginToken.objects.create(token="used", member=self.member)
        token.mark_used()

        token.refresh_from_db()
        self.assertTrue(token.is_used)
        self.assertIsNotNone(token.used_at)
        self.assertFalse(token.is_valid)

    def test_try_mark_used_claims_once(self):
        token = MagicLoginToken.objects.create(token="claim", member=self.member)

        first = token.try_mark_used()
        # Reload a separate instance to simulate a competing request.
        competitor = MagicLoginToken.objects.get(pk=token.pk)
        second = competitor.try_mark_used()

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertTrue(token.is_used)
        self.assertIsNotNone(token.used_at)
