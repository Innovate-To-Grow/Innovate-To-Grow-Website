import re
import time
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.test import Client, override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.authn.models import ContactEmail, Member
from apps.authn.tests.helpers import bearer_header, stale_bearer_headers
from apps.core.models import BackgroundJob
from apps.event.tests.helpers import make_member
from apps.mail.services.tokens.notifications import (
    send_subscription_confirmation,
    subscription_confirmation_dedupe_key,
)
from apps.mail.services.tokens.unsubscribe import (
    _MAX_AGE,
    _SALT,
    build_oneclick_unsubscribe_token,
    get_member_from_oneclick_token,
    load_resubscribe_token,
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


class OneClickUnsubscribePostTests(_UnsubscribeTestBase):
    def test_post_unsubscribes_every_address_of_the_member(self):
        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response["Content-Type"])
        self.assertEqual(
            self._flags(),
            {"unsub@example.com": False, "unsub-2@example.com": False, "unsub-3@example.com": False},
        )

    def test_post_leaves_other_members_untouched(self):
        other = make_member(email="bystander@example.com")

        self.client.post(self.url)

        self.assertEqual(self._flags(other), {"bystander@example.com": True})

    def test_post_does_not_delete_member(self):
        self.client.post(self.url)
        self.assertTrue(Member.objects.filter(pk=self.member.pk).exists())

    def test_one_click_post_never_reads_the_body(self):
        """RFC 8058 POSTs, the confirmation form and odd clients all work: the token is the whole request."""
        bodies = {
            "rfc8058 form body": {
                "data": "List-Unsubscribe=One-Click",
                "content_type": "application/x-www-form-urlencoded",
            },
            "multipart form": {"data": {"List-Unsubscribe": "One-Click"}},
            "multipart without boundary": {"data": "List-Unsubscribe=One-Click", "content_type": "multipart/form-data"},
            "json": {"data": '{"List-Unsubscribe": "One-Click"}', "content_type": "application/json"},
            "malformed json": {"data": "{not json", "content_type": "application/json"},
            "text/plain": {"data": "List-Unsubscribe=One-Click", "content_type": "text/plain"},
            "empty body": {},
        }
        for index, (label, kwargs) in enumerate(bodies.items()):
            with self.subTest(body=label):
                member, token = self._subscribed_member_with_token(f"body-{index}@example.com")

                response = self.client.post(f"/mail/unsubscribe/{token}/", **kwargs)

                self.assertEqual(response.status_code, 200)
                self.assertFalse(self._member_is_subscribed(member))

    def test_unusual_accept_header_or_format_param_still_unsubscribes(self):
        cases = {
            "accept text/plain": ({}, {"HTTP_ACCEPT": "text/plain"}),
            "accept xhtml only": ({}, {"HTTP_ACCEPT": "application/xhtml+xml"}),
            "format=json": ({"format": "json"}, {}),
            "format=unknown": ({"format": "foo"}, {}),
        }
        for index, (label, (query, headers)) in enumerate(cases.items()):
            with self.subTest(case=label):
                member, token = self._subscribed_member_with_token(f"accept-{index}@example.com")
                url = f"/mail/unsubscribe/{token}/"
                if query:
                    url += "?" + "&".join(f"{key}={value}" for key, value in query.items())

                self.assertEqual(self.client.get(url, **headers).status_code, 200)
                response = self.client.post(url, **headers)

                self.assertEqual(response.status_code, 200)
                self.assertIn("text/html", response["Content-Type"])
                self.assertFalse(self._member_is_subscribed(member))

    def test_replay_is_idempotent(self):
        first = self.client.post(self.url)
        second = self.client.post(self.url)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertContains(second, "You've been unsubscribed")
        self.assertFalse(self._member_is_subscribed(self.member))

    def test_footer_click_after_header_one_click_gets_success(self):
        self.client.post(self.url)  # Gmail's one-click header

        get_response = self.client.get(self.url)
        post_response = self.client.post(self.url)

        self.assertEqual(get_response.status_code, 200)
        self.assertContains(get_response, "You've been unsubscribed")
        self.assertEqual(post_response.status_code, 200)

    def test_already_unsubscribed_member_gets_success(self):
        ContactEmail.objects.filter(member=self.member).update(subscribe=False)

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You've been unsubscribed")

    def test_deactivated_member_can_unsubscribe(self):
        self.member.is_active = False
        self.member.save(update_fields=["is_active"])

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(self._member_is_subscribed(self.member))
        # The resubscribe link rejects inactive members, so none is offered.
        self.assertIsNone(_RESUBSCRIBE_FORM.search(response.content.decode()))

    def test_invalid_token_returns_400(self):
        response = self.client.post("/mail/unsubscribe/garbage-token/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("text/html", response["Content-Type"])

    def test_wrong_salt_token_returns_400(self):
        bad_token = signing.dumps({"member_id": str(self.member.pk)}, salt="wrong-salt")
        response = self.client.post(f"/mail/unsubscribe/{bad_token}/")
        self.assertEqual(response.status_code, 400)

    def test_nonexistent_member_returns_400(self):
        fake_token = signing.dumps({"member_id": str(uuid.uuid4())}, salt=_SALT)
        response = self.client.post(f"/mail/unsubscribe/{fake_token}/")
        self.assertEqual(response.status_code, 400)

    def test_token_payload_and_salt_are_unchanged(self):
        """Links already in inboxes carry exactly this payload under this salt."""
        legacy = signing.dumps({"member_id": str(self.member.pk)}, salt="rfc8058-one-click-unsubscribe", compress=True)

        response = self.client.post(f"/mail/unsubscribe/{legacy}/")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(self._member_is_subscribed(self.member))

    def test_responses_are_never_cached(self):
        responses = {
            "get": self.client.get(self.url),
            "post": self.client.post(self.url),
            "invalid": self.client.post("/mail/unsubscribe/garbage-token/"),
        }
        for label, response in responses.items():
            with self.subTest(response=label):
                self.assertIn("no-store", response["Cache-Control"])


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


class OneClickUnsubscribeConfirmationTests(_UnsubscribeTestBase):
    @patch("apps.authn.services.email.send_notification_email")
    def test_sends_confirmation_email_to_primary(self, mock_send):
        self.client.post(self.url)

        self.start_task.assert_called_once()
        self.assertTrue(self.start_task.call_args.kwargs["best_effort_start"])
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        self.assertEqual(call_kwargs["recipient"], "unsub@example.com")
        self.assertIn("unsubscribed", call_kwargs["subject"].lower())

    @patch("apps.authn.services.email.send_notification_email")
    def test_replay_sends_a_single_confirmation(self, mock_send):
        self.client.post(self.url)
        self.client.get(self.url)
        self.client.post(self.url)

        self.start_task.assert_called_once()
        mock_send.assert_called_once()

    @patch("apps.authn.services.email.send_notification_email")
    def test_get_sends_no_confirmation(self, mock_send):
        self.client.get(self.url)

        self.start_task.assert_not_called()
        mock_send.assert_not_called()

    @patch("apps.authn.services.email.send_notification_email")
    def test_already_unsubscribed_member_gets_no_email(self, mock_send):
        ContactEmail.objects.filter(member=self.member).update(subscribe=False)

        self.client.post(self.url)

        mock_send.assert_not_called()

    @patch("apps.authn.services.email.send_notification_email")
    def test_without_primary_confirmation_goes_to_the_oldest_changed_address(self, mock_send):
        member = Member.objects.create_user(password="x")
        older = ContactEmail.objects.create(member=member, email_address="older@example.com", email_type="other")
        ContactEmail.objects.create(member=member, email_address="newer@example.com", email_type="secondary")
        ContactEmail.objects.filter(pk=older.pk).update(created_at=timezone.now() - timedelta(days=1))

        self.client.post(f"/mail/unsubscribe/{build_oneclick_unsubscribe_token(member)}/")

        mock_send.assert_called_once()
        self.assertEqual(mock_send.call_args[1]["recipient"], "older@example.com")

    @patch("apps.authn.services.email.send_notification_email")
    def test_deactivated_member_gets_the_confirmation(self, mock_send):
        Member.objects.filter(pk=self.member.pk).update(is_active=False)

        self.client.post(self.url)

        mock_send.assert_called_once()

    @override_settings(BACKGROUND_JOBS_ENABLED=True)
    @patch("apps.authn.services.email.send_notification_email")
    def test_queues_confirmation_keyed_by_the_change_not_the_token(self, mock_send):
        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 200)
        mock_send.assert_not_called()
        job = BackgroundJob.objects.get(kind="authn.notification_email")
        self.assertRegex(job.dedupe_key, r"^subscription-confirmation:unsubscribe:[0-9a-f]{64}$")
        self.assertNotIn(self.token, job.dedupe_key)
        self.assertNotIn(self.token, str(job.payload))
        self.assertEqual(job.payload["recipient"], "unsub@example.com")

    @override_settings(BACKGROUND_JOBS_ENABLED=True)
    def test_replay_queues_a_single_confirmation(self):
        self.client.post(self.url)
        self.client.post(self.url)

        self.assertEqual(BackgroundJob.objects.filter(kind="authn.notification_email").count(), 1)

    def _toggle_loop(self, rounds):
        """One unsubscribe, then ``rounds`` of (resubscribe, unsubscribe) with the same two reusable links."""
        first = self.client.post(self.url)
        resubscribe_url = f"/mail/resubscribe/{_RESUBSCRIBE_FORM.search(first.content.decode()).group(1)}/"
        for _ in range(rounds):
            self.assertEqual(self.client.post(resubscribe_url).status_code, 200)
            self.assertEqual(self.client.post(self.url).status_code, 200)
        self.assertFalse(self._member_is_subscribed(self.member))  # every round was a real change

    def _queued_subjects(self):
        return [job.payload["subject"] for job in BackgroundJob.objects.filter(kind="authn.notification_email")]

    @override_settings(BACKGROUND_JOBS_ENABLED=True)
    def test_toggle_loop_queues_one_confirmation_per_action(self):
        """A forwarded link cannot flood the member: the outbox key collapses the loop within the hour."""
        middle_of_an_hour = timezone.now().replace(minute=30, second=0, microsecond=0)
        with patch("apps.mail.services.subscriptions.timezone.now", return_value=middle_of_an_hour):
            self._toggle_loop(rounds=10)

        subjects = self._queued_subjects()
        self.assertEqual(sum("unsubscribed" in subject for subject in subjects), 1)
        self.assertEqual(sum("resubscribed" in subject for subject in subjects), 1)

    @patch("apps.authn.services.email.send_notification_email")
    def test_toggle_loop_sends_one_confirmation_per_action_without_outbox(self, mock_send):
        self._toggle_loop(rounds=10)

        subjects = [call.kwargs["subject"] for call in mock_send.call_args_list]
        self.assertEqual(sum("unsubscribed" in subject for subject in subjects), 1)
        self.assertEqual(sum("resubscribed" in subject for subject in subjects), 1)

    @override_settings(BACKGROUND_JOBS_ENABLED=True)
    def test_change_in_a_later_hour_through_the_same_link_is_confirmed_again(self):
        first = self.client.post(self.url)
        resubscribe_token = _RESUBSCRIBE_FORM.search(first.content.decode()).group(1)
        self.client.post(f"/mail/resubscribe/{resubscribe_token}/")
        with patch("apps.mail.services.subscriptions.timezone.now", return_value=timezone.now() + timedelta(hours=2)):
            self.client.post(self.url)

        subjects = self._queued_subjects()
        self.assertEqual(sum("unsubscribed" in subject for subject in subjects), 2)
        self.assertEqual(sum("resubscribed" in subject for subject in subjects), 1)


class OneClickUnsubscribeAuthorizationHeaderTests(_UnsubscribeTestBase):
    def test_stale_bearer_does_not_block_unsubscribe(self):
        """The link token is the credential; a dead session's Bearer must never 401 it."""
        for index, (label, header) in enumerate(stale_bearer_headers().items()):
            with self.subTest(bearer=label):
                member, token = self._subscribed_member_with_token(f"stale-{index}@example.com")
                url = f"/mail/unsubscribe/{token}/"

                page = self.client.get(url, HTTP_AUTHORIZATION=header)
                self.assertEqual(page.status_code, 200)
                self.assertTrue(self._member_is_subscribed(member))  # GET only confirms

                response = self.client.post(url, HTTP_AUTHORIZATION=header)
                self.assertEqual(response.status_code, 200)
                self.assertFalse(self._member_is_subscribed(member))
                self.assertEqual(self.client.post(url, HTTP_AUTHORIZATION=header).status_code, 200)  # idempotent

    def test_bearer_of_another_member_unsubscribes_the_token_owner(self):
        member, token = self._subscribed_member_with_token("owner@example.com")

        response = self.client.post(f"/mail/unsubscribe/{token}/", HTTP_AUTHORIZATION=bearer_header(self.member))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(self._member_is_subscribed(member))
        self.assertTrue(self._is_subscribed())  # the signed-in member (setUp) is untouched


class OneClickUnsubscribeSessionCsrfTests(_UnsubscribeTestBase):
    def test_signed_in_browser_without_csrf_token_can_unsubscribe(self):
        """The confirmation form carries no CSRF token; a session cookie (e.g. a signed-in admin) must not 403 it."""
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.member)

        response = client.post(self.url, {"List-Unsubscribe": "One-Click"})

        self.assertEqual(response.status_code, 200)
        self.assertFalse(self._member_is_subscribed(self.member))


class SubscriptionConfirmationEmailTests(APITestCase):
    """The best-effort confirmation helper and its outbox key."""

    @patch("apps.mail.services.tokens.notifications.email_api.send_notification_email")
    def test_confirmation_skipped_without_any_address(self, mock_send):
        member = Member.objects.create_user(password="x")  # no ContactEmail
        self.assertEqual(member.get_primary_email(), "")

        for action in ("unsubscribe", "resubscribe"):
            with self.subTest(action=action):
                send_subscription_confirmation(
                    member=member, action=action, email_ids=[str(uuid.uuid4())], changed_at=timezone.now()
                )

        mock_send.assert_not_called()

    def test_unknown_action_is_rejected(self):
        member = make_member(email="action@example.com")
        with self.assertRaises(ValueError):
            send_subscription_confirmation(member=member, action="delete", email_ids=["x"], changed_at=timezone.now())

    def test_dedupe_key_is_one_per_member_action_and_hour(self):
        member_id = uuid.uuid4()
        start = datetime(2026, 10, 1, 10, 0, 5, tzinfo=UTC)

        def key(action="unsubscribe", *, member=member_id, changed_at=start):
            return subscription_confirmation_dedupe_key(action, member_id=member, changed_at=changed_at)

        self.assertRegex(key(), r"^subscription-confirmation:unsubscribe:[0-9a-f]{64}$")
        self.assertEqual(key(), key(changed_at=start + timedelta(minutes=59)))
        self.assertNotEqual(key(), key(changed_at=start + timedelta(hours=1)))
        self.assertNotEqual(key(), key("resubscribe"))
        self.assertNotEqual(key(), key(member=uuid.uuid4()))

    @override_settings(BACKGROUND_JOBS_ENABLED=True)
    def test_outbox_keeps_one_confirmation_per_window(self):
        member = make_member(email="window@example.com")
        email_ids = [str(ContactEmail.objects.get(member=member).pk)]
        start = datetime(2026, 10, 1, 10, 0, 5, tzinfo=UTC)

        for changed_at in (start, start + timedelta(minutes=30), start + timedelta(hours=1)):
            send_subscription_confirmation(
                member=member, action="unsubscribe", email_ids=email_ids, changed_at=changed_at
            )

        self.assertEqual(BackgroundJob.objects.filter(kind="authn.notification_email").count(), 2)

    @patch("apps.mail.services.tokens.notifications.start_in_process_task")
    def test_in_process_path_keeps_one_confirmation_per_window(self, start_task):
        cache.clear()  # also empties the throttle alias that holds the window marker
        member = make_member(email="window-local@example.com")
        email_ids = [str(ContactEmail.objects.get(member=member).pk)]

        for action in ("unsubscribe", "unsubscribe", "resubscribe", "resubscribe"):
            send_subscription_confirmation(member=member, action=action, email_ids=email_ids, changed_at=timezone.now())

        self.assertEqual(start_task.call_count, 2)
        self.assertEqual(
            [call.kwargs["name"] for call in start_task.call_args_list],
            [
                "subscription-confirmation-unsubscribe",
                "subscription-confirmation-resubscribe",
            ],
        )

    def test_dedupe_key_requires_a_known_action_and_time(self):
        with self.assertRaises(ValueError):
            subscription_confirmation_dedupe_key("unsubscribe", member_id=uuid.uuid4(), changed_at=None)
        with self.assertRaises(ValueError):
            subscription_confirmation_dedupe_key("other", member_id=uuid.uuid4(), changed_at=timezone.now())


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
