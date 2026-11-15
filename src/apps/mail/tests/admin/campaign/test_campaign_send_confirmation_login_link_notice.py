from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.event.tests.helpers import make_member, make_superuser
from apps.mail.tests.admin.campaign.test_campaign_send_confirmation import _make_campaign, _make_email_config


class CampaignSendConfirmationLoginLinkNoticeTest(TestCase):
    """The confirmation page says how many recipients get the sign-in page for {{login_link}} (no account)."""

    def setUp(self):
        cache.clear()
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        _make_email_config()
        make_member(email="member@example.edu", first_name="Mem", last_name="Ber")

    def _confirm_page(self, **kwargs):
        defaults = {"audience_type": "manual", "manual_emails": "Member@Example.edu\nstranger@example.edu"}
        campaign = _make_campaign(name="Login link notice", **{**defaults, **kwargs})
        return self.client.get(reverse("admin:mail_emailcampaign_send_confirm", args=[campaign.pk]))

    def test_recipients_without_an_account_are_counted_when_the_body_uses_the_login_link(self):
        response = self._confirm_page(body="Sign in: {{ login_link }}")

        self.assertContains(response, 'id="confirm-send-no-login-link"')
        self.assertContains(
            response, "1 recipient has no member account, so for that address <code>{{login_link}}</code>"
        )

    def test_the_subject_counts_too_and_the_count_is_plural(self):
        response = self._confirm_page(subject="{{login_link}}", manual_emails="a@example.edu\nb@example.edu")

        self.assertContains(response, "2 recipients have no member account, so for those addresses")

    def test_no_notice_when_every_recipient_has_an_account_or_the_link_is_unused(self):
        for kwargs in (
            {"body": "{{login_link}}", "manual_emails": "member@example.edu"},
            {"body": "No link here"},
        ):
            with self.subTest(**kwargs):
                self.assertNotContains(self._confirm_page(**kwargs), "confirm-send-no-login-link")
