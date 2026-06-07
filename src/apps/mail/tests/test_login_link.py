from datetime import timedelta
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.event.tests.helpers import make_event, make_member, make_registration, make_ticket
from apps.mail.models import EmailCampaign, LoginLinkToken
from apps.mail.services.login_links import issue_login_link, revoke_login_links
from apps.mail.utils.redirects import DEFAULT_LOGIN_REDIRECT_PATH


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


class ReusableLoginLinkTests(APITestCase):
    """Per-campaign reusable links: repeat logins, audit, and the kill switch."""

    def setUp(self):
        self.member = make_member(email="reuse@example.com")
        self.campaign = EmailCampaign.objects.create(
            subject="Reusable",
            body="b",
            login_link_reusable=True,
        )
        self.token = LoginLinkToken.generate_token()
        self.link = LoginLinkToken.objects.create(token=self.token, member=self.member, campaign=self.campaign)

    @patch("apps.mail.views.LoginLinkView.throttle_classes", [])
    def test_reusable_campaign_allows_repeat_logins(self):
        first = self.client.post("/mail/login-link/", {"token": self.token}, format="json")
        second = self.client.post("/mail/login-link/", {"token": self.token}, format="json")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.link.refresh_from_db()
        self.assertTrue(self.link.is_used)
        self.assertIsNotNone(self.link.used_at)

    @patch("apps.mail.views.LoginLinkView.throttle_classes", [])
    def test_repeat_login_updates_used_at(self):
        self.client.post("/mail/login-link/", {"token": self.token}, format="json")
        self.link.refresh_from_db()
        first_used_at = self.link.used_at

        self.client.post("/mail/login-link/", {"token": self.token}, format="json")
        self.link.refresh_from_db()
        self.assertGreaterEqual(self.link.used_at, first_used_at)

    @patch("apps.mail.views.LoginLinkView.throttle_classes", [])
    def test_unticking_reusable_acts_as_kill_switch(self):
        first = self.client.post("/mail/login-link/", {"token": self.token}, format="json")
        self.assertEqual(first.status_code, 200)

        self.campaign.login_link_reusable = False
        self.campaign.save(update_fields=["login_link_reusable", "updated_at"])

        blocked = self.client.post("/mail/login-link/", {"token": self.token}, format="json")
        self.assertEqual(blocked.status_code, 400)
        self.assertEqual(blocked.data["detail"], "This login link has already been used.")

    @patch("apps.mail.views.LoginLinkView.throttle_classes", [])
    def test_reusable_token_still_expires(self):
        self.link.expires_at = timezone.now() - timedelta(seconds=1)
        self.link.save(update_fields=["expires_at"])

        response = self.client.post("/mail/login-link/", {"token": self.token}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "This login link has expired.")

    @patch("apps.mail.views.LoginLinkView.throttle_classes", [])
    def test_reusable_login_rejected_for_inactive_member(self):
        self.member.is_active = False
        self.member.save(update_fields=["is_active", "updated_at"])

        response = self.client.post("/mail/login-link/", {"token": self.token}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "Invalid login link.")

    @patch("apps.mail.views.LoginLinkView.throttle_classes", [])
    def test_orphaned_token_degrades_to_one_time(self):
        # Campaign deleted -> SET_NULL -> reusable flag is gone; safest is one-time.
        self.campaign.delete()

        first = self.client.post("/mail/login-link/", {"token": self.token}, format="json")
        second = self.client.post("/mail/login-link/", {"token": self.token}, format="json")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 400)


class TicketLoginLinkReuseTests(APITestCase):
    """Registration-issued links read the reusable flag from the event."""

    def setUp(self):
        self.member = make_member(email="ticket@example.com")
        self.event = make_event()
        self.ticket = make_ticket(self.event)
        self.registration = make_registration(self.member, self.event, self.ticket)
        self.token = LoginLinkToken.generate_token()
        self.link = LoginLinkToken.objects.create(
            token=self.token,
            member=self.member,
            registration=self.registration,
            redirect_path="/event-registration",
        )

    @patch("apps.mail.views.LoginLinkView.throttle_classes", [])
    def test_event_reusable_default_allows_repeat_logins(self):
        first = self.client.post("/mail/login-link/", {"token": self.token}, format="json")
        second = self.client.post("/mail/login-link/", {"token": self.token}, format="json")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data["redirect_to"], "/event-registration")

    @patch("apps.mail.views.LoginLinkView.throttle_classes", [])
    def test_event_kill_switch_blocks_used_links(self):
        self.client.post("/mail/login-link/", {"token": self.token}, format="json")

        self.event.ticket_login_reusable = False
        self.event.save(update_fields=["ticket_login_reusable", "updated_at"])

        blocked = self.client.post("/mail/login-link/", {"token": self.token}, format="json")
        self.assertEqual(blocked.status_code, 400)


class LoginLinkServiceTests(APITestCase):
    def setUp(self):
        self.member = make_member(email="service@example.com")

    @override_settings(FRONTEND_URL="https://front.example.com/")
    def test_issue_login_link_builds_frontend_url(self):
        url = issue_login_link(member_id=self.member.pk, validity_days=7)

        link = LoginLinkToken.objects.get(member=self.member)
        self.assertEqual(url, f"https://front.example.com/login-link?token={link.token}")

    def test_issue_login_link_freezes_validity(self):
        before = timezone.now() + timedelta(days=21)
        issue_login_link(member_id=self.member.pk, validity_days=21)
        after = timezone.now() + timedelta(days=21)

        link = LoginLinkToken.objects.get(member=self.member)
        self.assertGreaterEqual(link.expires_at, before)
        self.assertLessEqual(link.expires_at, after)

    def test_issue_login_link_rejects_unsafe_redirect_path(self):
        issue_login_link(member_id=self.member.pk, validity_days=7, redirect_path="https://evil.example")

        link = LoginLinkToken.objects.get(member=self.member)
        self.assertEqual(link.redirect_path, "")
        self.assertEqual(link.effective_redirect_path, DEFAULT_LOGIN_REDIRECT_PATH)

    def test_issue_login_link_rejects_protocol_relative_redirect_path(self):
        issue_login_link(member_id=self.member.pk, validity_days=7, redirect_path="//evil.example")

        link = LoginLinkToken.objects.get(member=self.member)
        self.assertEqual(link.redirect_path, "")

    def test_revoke_login_links_expires_active_tokens(self):
        issue_login_link(member_id=self.member.pk, validity_days=7)
        link = LoginLinkToken.objects.get(member=self.member)

        revoked = revoke_login_links(LoginLinkToken.objects.all())

        self.assertEqual(revoked, 1)
        link.refresh_from_db()
        self.assertTrue(link.is_expired)

    def test_revoke_login_links_skips_already_expired(self):
        LoginLinkToken.objects.create(
            token="already-expired",
            member=self.member,
            expires_at=timezone.now() - timedelta(days=1),
        )

        revoked = revoke_login_links(LoginLinkToken.objects.all())
        self.assertEqual(revoked, 0)


class LoginLinkViewErrorTests(APITestCase):
    def setUp(self):
        self.member = make_member(email="err@example.com")

    @patch("apps.mail.views.LoginLinkView.throttle_classes", [])
    def test_missing_token_returns_400(self):
        response = self.client.post("/mail/login-link/", {"token": "  "}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "Token is required.")

    @patch("apps.mail.views.LoginLinkView.throttle_classes", [])
    def test_unknown_token_returns_400(self):
        response = self.client.post("/mail/login-link/", {"token": "does-not-exist"}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "Invalid login link.")


class LoginLinkTokenModelTests(APITestCase):
    def setUp(self):
        self.member = make_member(email="model@example.com")

    def test_str_active_and_expired(self):
        active = LoginLinkToken(token="t1", member=self.member)
        expired = LoginLinkToken(token="t2", member=self.member, expires_at=timezone.now() - timedelta(seconds=1))

        self.assertIn("active", str(active))
        self.assertIn("expired", str(expired))

    def test_is_valid_true_for_fresh_token(self):
        token = LoginLinkToken.objects.create(token="fresh", member=self.member)
        self.assertTrue(token.is_valid)

    def test_default_expiry_is_seven_days(self):
        before = timezone.now() + timedelta(days=7)
        token = LoginLinkToken.objects.create(token="default-expiry", member=self.member)
        after = timezone.now() + timedelta(days=7)

        self.assertGreaterEqual(token.expires_at, before)
        self.assertLessEqual(token.expires_at, after)

    def test_is_valid_false_when_used(self):
        token = LoginLinkToken.objects.create(token="used", member=self.member)
        token.mark_used()

        token.refresh_from_db()
        self.assertTrue(token.is_used)
        self.assertIsNotNone(token.used_at)
        self.assertFalse(token.is_valid)

    def test_try_mark_used_claims_once(self):
        token = LoginLinkToken.objects.create(token="claim", member=self.member)

        first = token.try_mark_used()
        # Reload a separate instance to simulate a competing request.
        competitor = LoginLinkToken.objects.get(pk=token.pk)
        second = competitor.try_mark_used()

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertTrue(token.is_used)
        self.assertIsNotNone(token.used_at)

    def test_record_reusable_use_does_not_consume(self):
        token = LoginLinkToken.objects.create(token="audit", member=self.member)

        self.assertTrue(token.record_reusable_use())
        token.refresh_from_db()
        self.assertTrue(token.is_used)
        first_used_at = token.used_at

        self.assertTrue(token.record_reusable_use())
        token.refresh_from_db()
        self.assertGreaterEqual(token.used_at, first_used_at)

    def test_record_reusable_use_fails_once_expired_or_revoked(self):
        token = LoginLinkToken.objects.create(
            token="revoked-mid-flight",
            member=self.member,
            expires_at=timezone.now() - timedelta(seconds=1),
        )

        self.assertFalse(token.record_reusable_use())
        token.refresh_from_db()
        self.assertFalse(token.is_used)

    def test_is_reusable_defaults_false_without_source(self):
        token = LoginLinkToken.objects.create(token="orphan", member=self.member)
        self.assertFalse(token.is_reusable)

    def test_unsafe_token_redirect_path_falls_back_to_default(self):
        token = LoginLinkToken.objects.create(token="unsafe", member=self.member, redirect_path="//evil.example")
        self.assertEqual(token.effective_redirect_path, DEFAULT_LOGIN_REDIRECT_PATH)
