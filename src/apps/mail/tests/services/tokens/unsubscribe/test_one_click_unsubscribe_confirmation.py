from datetime import timedelta
from unittest.mock import patch

from django.test import Client, override_settings
from django.utils import timezone

from apps.authn.models import ContactEmail, Member
from apps.authn.tests.helpers import bearer_header, stale_bearer_headers
from apps.core.models import BackgroundJob
from apps.mail.services.tokens.unsubscribe import (
    build_oneclick_unsubscribe_token,
)
from apps.mail.tests.services.tokens.unsubscribe.test_oneclick_unsubscribe import (
    _RESUBSCRIBE_FORM,
    _UnsubscribeTestBase,
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
