"""SMS short links: what a token is (random, short, stored as a digest), who gets a personal one, and what opening
one does (a single sign-in, a counted redirect, or a refusal that says nothing about its owner)."""

from datetime import timedelta
from unittest.mock import patch

from django.db import IntegrityError
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.event.tests.helpers import make_member, make_superuser
from apps.mail.models import SmsCampaign, SmsLinkToken
from apps.mail.services.sms import links


def token_of(url):
    return url.rsplit("/l/", 1)[1]


@override_settings(FRONTEND_URL="https://i2g.example.edu/")
class LinkShapeTests(SimpleTestCase):
    def test_a_link_is_the_short_path_and_a_128_bit_token(self):
        url = links.link_url("abc")
        self.assertEqual(url, "https://i2g.example.edu/l/abc")
        self.assertEqual(len(links.example_link()), len("https://i2g.example.edu/l/") + 22)

    def test_sign_in_paths_return_to_the_destination(self):
        self.assertEqual(links.sign_in_path("/account"), "/login")
        self.assertEqual(links.sign_in_path("/subscribe"), "/login?returnTo=/subscribe")
        self.assertEqual(
            links.sign_in_path("/event-registration?event=demo day"),
            "/login?returnTo=/event-registration%3Fevent%3Ddemo%20day",
        )
        self.assertEqual(links.sign_in_path("//evil.example"), "/login")
        self.assertEqual(links.sign_in_path("/" + "x" * 300), "/login")

    def test_event_pages_quote_the_slug(self):
        event = type("Event", (), {"slug": "fall/2026 demo"})()
        self.assertEqual(links.event_page_path(event), "/event-registration?event=fall%2F2026%20demo")


@override_settings(FRONTEND_URL="https://i2g.example.edu")
class IssueAndOpenTests(TestCase):
    def setUp(self):
        self.member = make_member(email="ada@example.com", first_name="Ada")
        self.campaign = SmsCampaign.objects.create(message="Hi {{login_link}}", audience_type="all_members")

    def test_a_personal_link_stores_only_its_digest_and_signs_in_once(self):
        url = links.issue_personal_link(
            purpose=links.Purpose.LOGIN, member=self.member, redirect_path="/subscribe", validity_days=3
        )
        token = token_of(url)
        row = SmsLinkToken.objects.get()
        self.assertEqual(len(token), 22)
        self.assertEqual(row.token_hash, links.token_digest(token))
        self.assertEqual(row.public_token, "")
        self.assertNotIn(token, str(row.__dict__))

        opened = links.open_link(token)
        self.assertEqual((opened.kind, opened.member, opened.redirect_to), ("sign_in", self.member, "/subscribe"))
        again = links.open_link(token)
        self.assertEqual((again.kind, again.code, again.redirect_to), ("rejected", "already_used", "/subscribe"))
        row.refresh_from_db()
        self.assertEqual(row.use_count, 1)

    def test_validity_is_bounded_by_the_settings_maximum(self):
        links.issue_personal_link(purpose=links.Purpose.LOGIN, member=self.member, redirect_path="/", validity_days=90)
        row = SmsLinkToken.objects.get()
        self.assertLessEqual(row.expires_at - timezone.now(), timedelta(days=14))

    def test_an_expired_link_is_refused_with_its_destination(self):
        url = links.issue_personal_link(
            purpose=links.Purpose.TICKET, member=self.member, redirect_path="/account", validity_days=1
        )
        SmsLinkToken.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        opened = links.open_link(token_of(url))
        self.assertEqual((opened.kind, opened.code, opened.redirect_to), ("rejected", "expired", "/account"))

    def test_staff_inactive_and_unknown_links_are_refused_alike(self):
        url = links.issue_personal_link(
            purpose=links.Purpose.LOGIN, member=self.member, redirect_path="/account", validity_days=1
        )
        self.member.is_active = False
        self.member.save(update_fields=["is_active"])
        for token in (token_of(url), "A" * 22, "short", "x" * 65, "has spaces in it!!!", ""):
            with self.subTest(token=token):
                opened = links.open_link(token)
                self.assertEqual((opened.kind, opened.code, opened.redirect_to), ("rejected", "invalid_link", ""))

    def test_staff_never_get_a_personal_link_and_a_promoted_member_cannot_use_one(self):
        with self.assertRaises(ValueError):
            links.issue_personal_link(
                purpose=links.Purpose.LOGIN, member=make_superuser(), redirect_path="/", validity_days=1
            )
        url = links.issue_personal_link(
            purpose=links.Purpose.LOGIN, member=self.member, redirect_path="/account", validity_days=1
        )
        self.member.is_staff = True
        self.member.save(update_fields=["is_staff"])
        self.assertEqual(links.open_link(token_of(url)).code, "invalid_link")

    def test_a_shared_link_is_made_once_per_campaign_and_counts_every_open(self):
        first = links.shared_link(
            campaign=self.campaign,
            purpose=links.Purpose.EVENT,
            redirect_path="/event-registration?event=x",
            validity_days=3,
        )
        second = links.shared_link(
            campaign=self.campaign, purpose=links.Purpose.EVENT, redirect_path="/other", validity_days=3
        )
        self.assertEqual(first, second)
        row = SmsLinkToken.objects.get()
        self.assertEqual(row.public_token, token_of(first))
        for _ in range(2):
            opened = links.open_link(token_of(first))
            self.assertEqual((opened.kind, opened.redirect_to), ("redirect", "/event-registration?event=x"))
        row.refresh_from_db()
        self.assertEqual(row.use_count, 2)
        self.assertIsNotNone(row.first_used_at)

    def test_a_shared_link_made_by_another_sender_meanwhile_is_reused(self):
        theirs = links.shared_link(
            campaign=self.campaign, purpose=links.Purpose.LOGIN, redirect_path="/login", validity_days=3
        )
        empty = SmsLinkToken.objects.none()
        with (
            patch.object(SmsLinkToken.objects, "filter", return_value=empty),
            patch.object(SmsLinkToken.objects, "create", side_effect=IntegrityError("duplicate")),
        ):
            mine = links.shared_link(
                campaign=self.campaign, purpose=links.Purpose.LOGIN, redirect_path="/login", validity_days=3
            )
        self.assertEqual(mine, theirs)

    def test_an_unsafe_destination_falls_back(self):
        links.issue_redirect_link(purpose=links.Purpose.TICKET, redirect_path="https://evil.example/x", validity_days=1)
        links.issue_personal_link(
            purpose=links.Purpose.LOGIN, member=self.member, redirect_path="//evil.example", validity_days=1
        )
        self.assertEqual(sorted(SmsLinkToken.objects.values_list("redirect_path", flat=True)), ["/account", "/login"])

    def test_revoking_expires_only_live_links(self):
        url = links.issue_personal_link(
            purpose=links.Purpose.LOGIN, member=self.member, redirect_path="/account", validity_days=1
        )
        self.assertEqual(links.revoke_links(SmsLinkToken.objects.all()), 1)
        self.assertEqual(links.revoke_links(SmsLinkToken.objects.all()), 0)
        self.assertEqual(links.open_link(token_of(url)).code, "expired")
