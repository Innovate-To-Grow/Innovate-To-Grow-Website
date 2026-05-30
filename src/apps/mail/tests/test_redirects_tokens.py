"""Coverage for redirect choices, unsubscribe/resubscribe token helpers, and converter dedup."""

import uuid
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.cms.models import CMSPage
from apps.event.tests.helpers import make_member
from apps.mail.services.audience.converters import members_to_recipients
from apps.mail.services.unsubscribe_token import (
    build_oneclick_unsubscribe_url,
    build_resubscribe_token,
    get_member_from_resubscribe_token,
)
from apps.mail.utils.redirects import (
    DEFAULT_LOGIN_REDIRECT_PATH,
    get_login_redirect_choices,
)


class LoginRedirectChoiceTests(TestCase):
    def test_published_cms_pages_included_and_archived_excluded(self):
        CMSPage.objects.create(slug="pub", route="/pub-route", title="Published Page", status="published")
        CMSPage.objects.create(slug="arch", route="/arch-route", title="Archived Page", status="archived")

        choices = dict(get_login_redirect_choices())

        self.assertIn(DEFAULT_LOGIN_REDIRECT_PATH, choices)
        self.assertIn("/pub-route", choices)
        self.assertNotIn("/arch-route", choices)

    def test_cms_page_with_unsafe_route_is_skipped(self):
        CMSPage.objects.create(slug="bad", route="not-internal", title="Bad Page", status="published")

        choices = dict(get_login_redirect_choices())

        self.assertNotIn("not-internal", choices)

    def test_duplicate_route_between_app_and_cms_is_deduplicated(self):
        # /schedule is already an APP_ROUTE; a CMS page with the same route should
        # not produce a second choice entry.
        CMSPage.objects.create(slug="dup", route="/schedule", title="Dup Schedule", status="published")

        choices = get_login_redirect_choices()
        schedule_entries = [c for c in choices if c[0] == "/schedule"]

        self.assertEqual(len(schedule_entries), 1)

    def test_cms_query_failure_is_swallowed(self):
        with patch(
            "apps.mail.utils.redirects.CMSPage.objects.filter",
            side_effect=RuntimeError("db down"),
        ):
            choices = dict(get_login_redirect_choices())

        # Still returns app routes + default without raising.
        self.assertIn(DEFAULT_LOGIN_REDIRECT_PATH, choices)

    def test_current_path_appended_when_not_already_present(self):
        choices = dict(get_login_redirect_choices(current_path="/custom-destination"))

        self.assertIn("/custom-destination", choices)
        self.assertEqual(choices["/custom-destination"], "Current selection (/custom-destination)")

    def test_current_path_not_duplicated_when_already_present(self):
        choices = get_login_redirect_choices(current_path=DEFAULT_LOGIN_REDIRECT_PATH)
        default_entries = [c for c in choices if c[0] == DEFAULT_LOGIN_REDIRECT_PATH]

        self.assertEqual(len(default_entries), 1)

    def test_app_route_skipped_when_unsafe_or_duplicate(self):
        fake_routes = [
            {"url": "not-internal", "title": "Bad"},  # unsafe -> skipped
            {"url": DEFAULT_LOGIN_REDIRECT_PATH, "title": "Dup Account"},  # already seen -> skipped
            {"url": "/unique-route", "title": "Unique"},  # included
        ]
        with patch("apps.mail.utils.redirects.APP_ROUTES", fake_routes):
            choices = dict(get_login_redirect_choices())

        self.assertNotIn("not-internal", choices)
        self.assertIn("/unique-route", choices)
        # The default still appears exactly once despite the duplicate app route.
        self.assertEqual(choices[DEFAULT_LOGIN_REDIRECT_PATH], f"Account ({DEFAULT_LOGIN_REDIRECT_PATH})")


class ResubscribeTokenTests(TestCase):
    def test_unknown_member_raises_account_not_found(self):
        token = build_resubscribe_token(uuid.uuid4())

        with self.assertRaisesMessage(ValueError, "Account not found."):
            get_member_from_resubscribe_token(token)

    def test_valid_token_returns_member(self):
        member = make_member(email="resub2@example.com")
        token = build_resubscribe_token(member)

        self.assertEqual(get_member_from_resubscribe_token(token).pk, member.pk)


class OneClickUrlTests(TestCase):
    @override_settings(BACKEND_URL="")
    def test_empty_backend_url_returns_empty_string(self):
        member = make_member(email="unsub@example.com")

        self.assertEqual(build_oneclick_unsubscribe_url(member), "")

    @override_settings(BACKEND_URL="https://api.example.com/")
    def test_configured_backend_url_builds_absolute_url(self):
        member = make_member(email="unsub2@example.com")

        url = build_oneclick_unsubscribe_url(member)

        self.assertTrue(url.startswith("https://api.example.com/mail/unsubscribe/"))
        self.assertTrue(url.endswith("/"))


class MembersToRecipientsDedupTests(TestCase):
    def test_repeated_member_email_is_deduplicated(self):
        member = make_member(email="dup@example.com", first_name="Dup", last_name="User")

        # The same member appearing twice in the iterable exercises the
        # "email already seen" dedup branch.
        recipients = members_to_recipients([member, member], send_all=False)

        emails = [r["email"] for r in recipients]
        self.assertEqual(emails, ["dup@example.com"])
