import re
import time
from unittest.mock import patch

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from rest_framework.test import APITestCase

from apps.authn.models import ContactEmail, Member
from apps.core.models import BackgroundJob
from apps.event.tests.helpers import make_member
from apps.mail.services.tokens.unsubscribe import (
    _MAX_AGE,
    build_oneclick_unsubscribe_token,
    get_member_from_oneclick_token,
)

_RESUBSCRIBE_FORM = re.compile(r'<form method="post" action="\.\./\.\./resubscribe/([^/"]+)/"')


def _aged_token(member, age_seconds):
    """An unsubscribe token as if it had been issued ``age_seconds`` ago."""
    issued = signing.b62_encode(int(time.time()) - age_seconds)
    with patch.object(signing.TimestampSigner, "timestamp", return_value=issued):
        return build_oneclick_unsubscribe_token(member)


class _UnsubscribeTestBase(APITestCase):
    def setUp(self):
        cache.clear()
        task_patcher = patch(
            "apps.mail.services.tokens.notifications.start_in_process_task",
            side_effect=lambda target, *args, **_kwargs: target(*args),
        )
        self.start_task = task_patcher.start()
        self.addCleanup(task_patcher.stop)
        self.member = make_member(email="unsub@example.com", first_name="Una")
        self.primary_email = ContactEmail.objects.get(member=self.member, email_type="primary")
        self.secondary_email = ContactEmail.objects.create(
            member=self.member, email_address="unsub-2@example.com", email_type="secondary", subscribe=True
        )
        self.other_email = ContactEmail.objects.create(
            member=self.member, email_address="unsub-3@example.com", email_type="other", subscribe=False
        )
        self.token = build_oneclick_unsubscribe_token(self.member)
        self.url = f"/mail/unsubscribe/{self.token}/"

    def _flags(self, member=None):
        rows = ContactEmail.objects.filter(member=member or self.member)
        return {row.email_address: row.subscribe for row in rows}

    def _is_subscribed(self):
        self.primary_email.refresh_from_db()
        return self.primary_email.subscribe

    def _subscribed_member_with_token(self, email):
        member = make_member(email=email)
        return member, build_oneclick_unsubscribe_token(member)

    @staticmethod
    def _member_is_subscribed(member):
        return ContactEmail.objects.filter(member=member, subscribe=True).exists()


class OneClickUnsubscribeExpiryTests(_UnsubscribeTestBase):
    def test_max_age_is_365_days(self):
        self.assertEqual(_MAX_AGE, 60 * 60 * 24 * 365)

    def test_token_older_than_the_old_90_day_limit_still_works(self):
        token = _aged_token(self.member, 100 * 24 * 60 * 60)

        response = self.client.post(f"/mail/unsubscribe/{token}/")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(self._member_is_subscribed(self.member))

    def test_token_just_inside_365_days_works(self):
        token = _aged_token(self.member, _MAX_AGE - 60)

        self.assertEqual(get_member_from_oneclick_token(token).pk, self.member.pk)
        self.assertEqual(self.client.post(f"/mail/unsubscribe/{token}/").status_code, 200)

    def test_token_just_past_365_days_is_rejected(self):
        token = _aged_token(self.member, _MAX_AGE + 60)

        with self.assertRaisesMessage(ValueError, "Invalid or expired unsubscribe link."):
            get_member_from_oneclick_token(token)
        response = self.client.post(f"/mail/unsubscribe/{token}/")
        self.assertEqual(response.status_code, 400)
        self.assertTrue(self._is_subscribed())


class OneClickUnsubscribeGetTests(_UnsubscribeTestBase):
    def test_get_has_no_side_effects(self):
        before = self._flags()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response["Content-Type"])
        self.assertEqual(self._flags(), before)
        self.start_task.assert_not_called()
        self.assertFalse(BackgroundJob.objects.exists())

    def test_get_renders_confirmation_form_posting_to_the_same_url(self):
        response = self.client.get(self.url)
        html = response.content.decode()

        form = re.search(r"<form\b[^>]*>", html).group(0)
        self.assertIn('method="post"', form)
        self.assertNotIn("action=", form)  # posts back to this page's own URL
        self.assertRegex(html, r'<button type="submit"[^>]*>Unsubscribe</button>')
        # The view is CSRF-exempt and cookie-free: no CSRF token or cookie on a page scanners fetch.
        self.assertNotIn("csrfmiddlewaretoken", html)
        self.assertNotIn(settings.CSRF_COOKIE_NAME, response.cookies)

    def test_confirmation_form_post_unsubscribes(self):
        page = self.client.get(self.url)
        self.assertEqual(page.status_code, 200)

        response = self.client.post(self.url, "", content_type="application/x-www-form-urlencoded")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(self._member_is_subscribed(self.member))

    def test_head_has_no_side_effects(self):
        before = self._flags()

        response = self.client.head(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._flags(), before)
        self.start_task.assert_not_called()

    def test_options_is_not_allowed_and_changes_nothing(self):
        before = self._flags()

        response = self.client.options(self.url)

        self.assertEqual(response.status_code, 405)
        self.assertEqual(self._flags(), before)

    def test_get_when_nothing_is_subscribed_shows_done_page_without_resubscribe(self):
        ContactEmail.objects.filter(member=self.member).update(subscribe=False)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You've been unsubscribed")
        self.assertNotContains(response, "<form")

    def test_get_counts_any_subscribed_address_not_only_the_primary(self):
        ContactEmail.objects.filter(pk=self.primary_email.pk).update(subscribe=False)

        response = self.client.get(self.url)

        self.assertContains(response, "Unsubscribe from newsletters?")

    def test_get_invalid_token_returns_400_html(self):
        response = self.client.get("/mail/unsubscribe/garbage-token/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("text/html", response["Content-Type"])

    def test_member_first_name_is_escaped(self):
        Member.objects.filter(pk=self.member.pk).update(first_name="<script>alert(1)</script>")

        for method in ("get", "post"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(self.url)
                self.assertNotContains(response, "<script>alert(1)</script>")
                self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")
