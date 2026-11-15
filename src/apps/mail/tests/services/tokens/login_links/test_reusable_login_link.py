from datetime import timedelta

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.event.tests.helpers import make_event, make_member, make_registration, make_ticket
from apps.mail.models import EmailCampaign, LoginLinkToken
from apps.mail.redirects import DEFAULT_LOGIN_REDIRECT_PATH
from apps.mail.services.tokens.login_links import issue_login_link, revoke_login_links


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

    def test_reusable_campaign_allows_repeat_logins(self):
        first = self.client.post("/mail/login-link/", {"token": self.token}, format="json")
        second = self.client.post("/mail/login-link/", {"token": self.token}, format="json")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.link.refresh_from_db()
        self.assertTrue(self.link.is_used)
        self.assertIsNotNone(self.link.used_at)

    def test_repeat_login_updates_used_at(self):
        self.client.post("/mail/login-link/", {"token": self.token}, format="json")
        self.link.refresh_from_db()
        first_used_at = self.link.used_at

        self.client.post("/mail/login-link/", {"token": self.token}, format="json")
        self.link.refresh_from_db()
        self.assertGreaterEqual(self.link.used_at, first_used_at)

    def test_unticking_reusable_acts_as_kill_switch(self):
        first = self.client.post("/mail/login-link/", {"token": self.token}, format="json")
        self.assertEqual(first.status_code, 200)

        self.campaign.login_link_reusable = False
        self.campaign.save(update_fields=["login_link_reusable", "updated_at"])

        blocked = self.client.post("/mail/login-link/", {"token": self.token}, format="json")
        self.assertEqual(blocked.status_code, 400)
        self.assertEqual(blocked.data["detail"], "This login link has already been used.")

    def test_reusable_token_still_expires(self):
        self.link.expires_at = timezone.now() - timedelta(seconds=1)
        self.link.save(update_fields=["expires_at"])

        response = self.client.post("/mail/login-link/", {"token": self.token}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "This login link has expired.")

    def test_reusable_login_rejected_for_inactive_member(self):
        self.member.is_active = False
        self.member.save(update_fields=["is_active", "updated_at"])

        response = self.client.post("/mail/login-link/", {"token": self.token}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "Invalid login link.")

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

    def test_event_reusable_default_allows_repeat_logins(self):
        first = self.client.post("/mail/login-link/", {"token": self.token}, format="json")
        second = self.client.post("/mail/login-link/", {"token": self.token}, format="json")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data["redirect_to"], "/event-registration")

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
        self.assertEqual(url, f"https://front.example.com/login-link#token={link.token}")

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

    def test_missing_token_returns_400(self):
        response = self.client.post("/mail/login-link/", {"token": "  "}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "Token is required.")

    def test_unknown_token_returns_400(self):
        response = self.client.post("/mail/login-link/", {"token": "does-not-exist"}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "Invalid login link.")
