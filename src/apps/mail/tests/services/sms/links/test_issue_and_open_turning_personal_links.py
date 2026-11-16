from django.test import override_settings
from django.utils import timezone

from apps.mail.models import SmsLinkToken
from apps.mail.services.sms import links
from apps.mail.tests.services.sms.links.test_issue_and_open import _IssueAndOpenCase
from apps.mail.tests.services.sms.links.test_links import PHONE, token_of

from ..policy.policy_helpers import sms_settings


@override_settings(FRONTEND_URL="https://i2g.example.edu")
class IssueAndOpenTests(_IssueAndOpenCase):
    def test_turning_personal_links_off_revokes_the_ones_already_texted_for_good(self):
        for switches in ({"personal_links_enabled": False}, {"links_enabled": False}):
            with self.subTest(switches=switches):
                sms_settings(links_enabled=True, personal_links_enabled=True)
                url = links.issue_personal_link(
                    purpose=links.Purpose.LOGIN,
                    member=self.member,
                    phone=PHONE,
                    redirect_path="/subscribe",
                    validity_days=3,
                )
                token = token_of(url)
                sms_settings(**switches)
                # It opens the sign-in page, returning to its page, and signs nobody in.
                opened = links.open_link(token)
                self.assertEqual((opened.kind, opened.member), ("redirect", None))
                self.assertEqual(opened.redirect_to, "/login?returnTo=/subscribe")
                # Turned on again before it would have expired, it still signs nobody in.
                sms_settings(links_enabled=True, personal_links_enabled=True)
                self.assertEqual(links.open_link(token).kind, "redirect")
                row = SmsLinkToken.objects.get(token_hash=links.token_digest(token))
                self.assertIsNotNone(row.revoked_at)
                self.assertEqual((row.first_used_at, row.use_count), (None, 0))

    def test_revoking_expires_only_live_links(self):
        url = links.issue_personal_link(
            purpose=links.Purpose.LOGIN, member=self.member, phone=PHONE, redirect_path="/account", validity_days=1
        )
        self.assertEqual(links.revoke_links(SmsLinkToken.objects.all()), 1)
        self.assertEqual(links.revoke_links(SmsLinkToken.objects.all()), 0)
        row = SmsLinkToken.objects.get()
        self.assertIsNotNone(row.revoked_at)
        self.assertLessEqual(row.expires_at, timezone.now())
        # A revoked personal link opens the sign-in page and signs nobody in ("/account" is where it lands anyway).
        opened = links.open_link(token_of(url))
        self.assertEqual((opened.kind, opened.member, opened.redirect_to), ("redirect", None, "/login"))

    def test_a_revoked_shared_link_is_refused_as_expired(self):
        url = links.shared_link(
            campaign=self.campaign,
            purpose=links.Purpose.EVENT,
            redirect_path="/event-registration?event=x",
            validity_days=3,
        )
        SmsLinkToken.objects.update(revoked_at=timezone.now())  # revoked, though its expiry is still ahead
        opened = links.open_link(token_of(url))
        self.assertEqual((opened.kind, opened.code), ("rejected", "expired"))

    def test_with_personal_links_off_none_is_issued(self):
        sms_settings(personal_links_enabled=False)
        url = links.issue_personal_link(
            purpose=links.Purpose.LOGIN, member=self.member, phone=PHONE, redirect_path="/", validity_days=1
        )
        self.assertIsNone(url)
        self.assertFalse(SmsLinkToken.objects.exists())
