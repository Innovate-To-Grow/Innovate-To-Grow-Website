"""Admin coverage for login-link revocation surfaces."""

from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.event.tests.helpers import make_event, make_member, make_registration, make_superuser, make_ticket
from apps.mail.admin.login_link import LoginLinkTokenAdmin
from apps.mail.models import EmailCampaign, LoginLinkToken


class LoginLinkTokenAdminTests(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.member = make_member(email="links@example.com")
        self.campaign = EmailCampaign.objects.create(subject="s", body="b")
        self.link = LoginLinkToken.objects.create(token="admin-token", member=self.member, campaign=self.campaign)

    def test_changelist_renders_without_exposing_raw_token(self):
        response = self.client.get(reverse("admin:mail_loginlinktoken_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "admin-token")

    def test_change_view_excludes_raw_token(self):
        response = self.client.get(reverse("admin:mail_loginlinktoken_change", args=[self.link.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "admin-token")

    def test_revoke_action_expires_selected_links(self):
        response = self.client.post(
            reverse("admin:mail_loginlinktoken_changelist"),
            {"action": "revoke_selected_action", "_selected_action": [self.link.pk]},
            follow=True,
        )

        self.assertContains(response, "Revoked 1 login link(s).")
        self.link.refresh_from_db()
        self.assertTrue(self.link.is_expired)

    def test_status_badge_states(self):
        admin = LoginLinkTokenAdmin(LoginLinkToken, None)

        self.assertEqual(admin.status_badge(self.link), "active")

        self.link.is_used = True
        self.assertEqual(admin.status_badge(self.link), "used")

        self.link.expires_at = timezone.now() - timedelta(seconds=1)
        self.assertEqual(admin.status_badge(self.link), "expired")

    def test_admin_is_read_only(self):
        response = self.client.get(reverse("admin:mail_loginlinktoken_add"))
        self.assertEqual(response.status_code, 403)


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class CampaignRevokeActionTests(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.member = make_member(email="campaign-revoke@example.com")
        self.campaign = EmailCampaign.objects.create(subject="s", body="b")
        self.other_campaign = EmailCampaign.objects.create(subject="other", body="b")
        self.link = LoginLinkToken.objects.create(token="t-camp", member=self.member, campaign=self.campaign)
        self.other_link = LoginLinkToken.objects.create(
            token="t-other", member=self.member, campaign=self.other_campaign
        )

    def test_revoke_action_only_touches_selected_campaigns(self):
        response = self.client.post(
            reverse("admin:mail_emailcampaign_changelist"),
            {"action": "revoke_login_links_action", "_selected_action": [self.campaign.pk]},
            follow=True,
        )

        self.assertContains(response, "Revoked 1 login link(s).")
        self.link.refresh_from_db()
        self.other_link.refresh_from_db()
        self.assertTrue(self.link.is_expired)
        self.assertFalse(self.other_link.is_expired)


@override_settings(ADMIN_REQUIRE_CONFIRMATION=False)
class RegistrationRevokeActionTests(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        self.member = make_member(email="reg-revoke@example.com")
        self.event = make_event()
        self.ticket = make_ticket(self.event)
        self.registration = make_registration(self.member, self.event, self.ticket)
        self.link = LoginLinkToken.objects.create(token="t-reg", member=self.member, registration=self.registration)

    def test_revoke_action_expires_registration_links(self):
        response = self.client.post(
            reverse("admin:event_eventregistration_changelist"),
            {"action": "revoke_login_links_action", "_selected_action": [self.registration.pk]},
            follow=True,
        )

        self.assertContains(response, "Revoked 1 login link(s).")
        self.link.refresh_from_db()
        self.assertTrue(self.link.is_expired)
