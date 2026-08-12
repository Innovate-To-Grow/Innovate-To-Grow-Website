from unittest.mock import patch

from django.core import signing
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.authn.models import ContactEmail, Member
from apps.core.models import BackgroundJob
from apps.event.tests.helpers import make_member
from apps.mail.services.tokens.notifications import subscription_confirmation_dedupe_key
from apps.mail.services.tokens.unsubscribe import (
    _SALT,
    build_oneclick_unsubscribe_token,
)


class OneClickUnsubscribeViewTests(APITestCase):
    def setUp(self):
        task_patcher = patch(
            "apps.mail.services.tokens.notifications.start_in_process_task",
            side_effect=lambda target, *args, **_kwargs: target(*args),
        )
        self.start_task = task_patcher.start()
        self.addCleanup(task_patcher.stop)
        self.member = make_member(email="unsub@example.com")
        # Set primary email as subscribed so we can test unsubscribe
        self.primary_email = ContactEmail.objects.get(member=self.member, email_type="primary")
        self.primary_email.subscribe = True
        self.primary_email.save(update_fields=["subscribe"])
        self.token = build_oneclick_unsubscribe_token(self.member)
        self.url = f"/mail/unsubscribe/{self.token}/"

    def _is_subscribed(self):
        self.primary_email.refresh_from_db()
        return self.primary_email.subscribe

    def test_valid_post_unsubscribes_member(self):
        self.assertTrue(self._is_subscribed())

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(self._is_subscribed())

    def test_replay_post_returns_400(self):
        """Posting the same token twice should fail on the second attempt (one-time use)."""
        self.client.post(self.url)
        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(self._is_subscribed())

    def test_get_unsubscribes_member(self):
        """GET directly unsubscribes the member."""
        self.assertTrue(self._is_subscribed())

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response["Content-Type"])
        self.assertContains(response, "csrfmiddlewaretoken")
        self.assertFalse(self._is_subscribed())

    def test_get_replay_returns_400(self):
        """GET with an already-used token returns 400."""
        self.client.get(self.url)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 400)

    def test_get_invalid_token_returns_400_html(self):
        response = self.client.get("/mail/unsubscribe/garbage-token/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("text/html", response["Content-Type"])

    def test_invalid_token_returns_400(self):
        response = self.client.post("/mail/unsubscribe/garbage-token/")
        self.assertEqual(response.status_code, 400)

    def test_wrong_salt_token_returns_400(self):
        bad_token = signing.dumps({"member_id": str(self.member.pk)}, salt="wrong-salt")
        response = self.client.post(f"/mail/unsubscribe/{bad_token}/")
        self.assertEqual(response.status_code, 400)

    def test_nonexistent_member_returns_400(self):
        import uuid

        fake_token = signing.dumps({"member_id": str(uuid.uuid4())}, salt=_SALT)
        response = self.client.post(f"/mail/unsubscribe/{fake_token}/")
        self.assertEqual(response.status_code, 400)

    def test_inactive_member_returns_400(self):
        self.member.is_active = False
        self.member.save(update_fields=["is_active"])

        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 400)

    def test_does_not_delete_member(self):
        self.client.post(self.url)
        self.assertTrue(Member.objects.filter(pk=self.member.pk).exists())

    @patch("apps.authn.services.email.send_notification_email")
    def test_sends_confirmation_email(self, mock_send):
        self.client.post(self.url)

        self.start_task.assert_called_once()
        self.assertTrue(self.start_task.call_args.kwargs["best_effort_start"])
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        self.assertEqual(call_kwargs["recipient"], "unsub@example.com")
        self.assertIn("unsubscribed", call_kwargs["subject"].lower())

    @patch("apps.authn.services.email.send_notification_email")
    def test_replay_post_does_not_resend_email(self, mock_send):
        """Second POST is rejected (token consumed), so no confirmation email is sent."""
        self.client.post(self.url)
        self.start_task.reset_mock()
        mock_send.reset_mock()

        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 400)
        self.start_task.assert_not_called()
        mock_send.assert_not_called()

    @override_settings(BACKGROUND_JOBS_ENABLED=True)
    @patch("apps.authn.services.email.send_notification_email")
    def test_queues_confirmation_with_token_derived_dedupe_key(self, mock_send):
        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 200)
        mock_send.assert_not_called()
        job = BackgroundJob.objects.get(kind="authn.notification_email")
        self.assertEqual(
            job.dedupe_key,
            subscription_confirmation_dedupe_key("unsubscribe", self.token),
        )
        self.assertEqual(job.payload["recipient"], "unsub@example.com")


class SubscriptionConfirmationEmailTests(APITestCase):
    """The best-effort confirmation helpers skip members without a primary email."""

    @patch("apps.mail.services.tokens.notifications.email_api.send_notification_email")
    def test_unsubscribe_confirmation_skipped_without_primary_email(self, mock_send):
        from apps.mail.views.subscriptions import _send_unsubscribe_confirmation

        member = Member.objects.create_user(password="x")  # no ContactEmail
        self.assertEqual(member.get_primary_email(), "")

        _send_unsubscribe_confirmation(member, "event-token")

        mock_send.assert_not_called()

    @patch("apps.mail.services.tokens.notifications.email_api.send_notification_email")
    def test_resubscribe_confirmation_skipped_without_primary_email(self, mock_send):
        from apps.mail.views.subscriptions import _send_resubscribe_confirmation

        member = Member.objects.create_user(password="x")  # no ContactEmail

        _send_resubscribe_confirmation(member, "event-token")

        mock_send.assert_not_called()
