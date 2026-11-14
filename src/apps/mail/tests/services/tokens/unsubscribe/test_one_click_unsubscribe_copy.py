import re
from unittest.mock import patch

from django.conf import settings
from django.test import Client, override_settings

from apps.authn.models import ContactEmail, Member
from apps.mail.services.tokens.unsubscribe import (
    build_oneclick_unsubscribe_token,
    load_resubscribe_token,
)
from apps.mail.tests.services.tokens.unsubscribe.test_oneclick_unsubscribe import (
    _RESUBSCRIBE_FORM,
    _UnsubscribeTestBase,
)


class OneClickUnsubscribeCopyTests(_UnsubscribeTestBase):
    @override_settings(FRONTEND_URL="https://site.example")
    def test_done_page_is_honest_and_links_to_account(self):
        response = self.client.post(self.url)

        self.assertContains(response, "all email addresses on your Innovate to Grow account")
        self.assertContains(response, "Innovate to Grow newsletters")
        self.assertContains(response, "events you registered for")
        self.assertContains(response, "program announcements")
        self.assertContains(response, 'href="https://site.example/account"')

    @override_settings(FRONTEND_URL="https://site.example")
    def test_pages_never_list_the_member_addresses(self):
        pages = {"confirm": self.client.get(self.url), "done": self.client.post(self.url)}
        for label, response in pages.items():
            with self.subTest(page=label):
                for address in ("unsub@example.com", "unsub-2@example.com", "unsub-3@example.com"):
                    self.assertNotContains(response, address)

    @override_settings(FRONTEND_URL="https://site.example")
    def test_invalid_link_page_links_to_email_preferences(self):
        response = self.client.get("/mail/unsubscribe/garbage-token/")

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Manage email preferences", status_code=400)
        self.assertContains(response, 'href="https://site.example/account"', status_code=400)

    @override_settings(FRONTEND_URL="")
    def test_pages_render_without_frontend_url(self):
        self.assertEqual(self.client.get("/mail/unsubscribe/garbage-token/").status_code, 400)
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "/account")

    @override_settings(
        CSP_REPORT_ONLY=False,
        MIDDLEWARE=[*settings.MIDDLEWARE, "apps.core.middleware.ContentSecurityPolicyMiddleware"],
    )
    def test_enforcing_csp_nonces_the_confirmation_and_done_pages(self):
        client = Client()
        for label, response in {"confirm": client.get(self.url), "done": client.post(self.url)}.items():
            with self.subTest(page=label):
                nonce = re.search(r"'nonce-([^']+)'", response["Content-Security-Policy"]).group(1)
                style_tags = re.findall(r"<style\b[^>]*>", response.content.decode(), flags=re.IGNORECASE)
                self.assertTrue(style_tags)
                self.assertTrue(all(f'nonce="{nonce}"' in tag for tag in style_tags))


class OneClickUnsubscribeResubscribeOfferTests(_UnsubscribeTestBase):
    def _offered_ids(self, response):
        match = _RESUBSCRIBE_FORM.search(response.content.decode())
        self.assertIsNotNone(match, "the done page should offer a resubscribe button")
        member, email_ids = load_resubscribe_token(match.group(1))
        self.assertEqual(member.pk, self.member.pk)
        return set(email_ids)

    def test_offer_restores_exactly_the_addresses_this_post_turned_off(self):
        response = self.client.post(self.url)

        # The "other" address was already off, so it is not part of the undo.
        self.assertEqual(self._offered_ids(response), {str(self.primary_email.pk), str(self.secondary_email.pk)})

    def test_replay_offers_no_resubscribe_button(self):
        self.client.post(self.url)

        response = self.client.post(self.url)

        self.assertContains(response, "You've been unsubscribed")
        self.assertIsNone(_RESUBSCRIBE_FORM.search(response.content.decode()))

    def test_post_for_a_member_who_opted_out_elsewhere_offers_no_button(self):
        """A forwarded link must not turn a deliberate opt-out (e.g. on /account) back on."""
        ContactEmail.objects.filter(member=self.member).update(subscribe=False)

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<form")
        self.assertEqual(
            self._flags(),
            {"unsub@example.com": False, "unsub-2@example.com": False, "unsub-3@example.com": False},
        )

    def test_replay_without_primary_offers_no_button(self):
        member = Member.objects.create_user(password="x", first_name="Nope")
        ContactEmail.objects.create(member=member, email_address="only-other@example.com", email_type="other")
        url = f"/mail/unsubscribe/{build_oneclick_unsubscribe_token(member)}/"
        self.client.post(url)

        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(_RESUBSCRIBE_FORM.search(response.content.decode()))

    def test_offered_button_resubscribes_through_the_relative_url(self):
        response = self.client.post(self.url)
        token = _RESUBSCRIBE_FORM.search(response.content.decode()).group(1)

        resubscribe = self.client.post(f"/mail/resubscribe/{token}/")

        self.assertEqual(resubscribe.status_code, 200)
        self.assertEqual(
            self._flags(),
            {"unsub@example.com": True, "unsub-2@example.com": True, "unsub-3@example.com": False},
        )


class SubscriptionChangesSyncTheMemberSheetTests(_UnsubscribeTestBase):
    """The flags change with a bulk UPDATE, which sends no ``post_save``: the sheet sync must still be scheduled."""

    @patch("apps.authn.services.members.sheet_sync.schedule_member_sync")
    def test_unsubscribe_and_resubscribe_schedule_the_member_sheet_sync(self, mock_sync):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_sync.call_count, 1)

        resubscribe_url = re.search(r'action="\.\./\.\./resubscribe/([^/"]+)/"', response.content.decode())
        self.assertIsNotNone(resubscribe_url)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(f"/mail/resubscribe/{resubscribe_url.group(1)}/")
        self.assertEqual(mock_sync.call_count, 2)

    @patch("apps.authn.services.members.sheet_sync.schedule_member_sync")
    def test_a_replay_that_changes_nothing_schedules_no_sync(self, mock_sync):
        self.client.post(self.url)
        mock_sync.reset_mock()

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(self.url)

        mock_sync.assert_not_called()
