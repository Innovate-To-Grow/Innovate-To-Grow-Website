from unittest.mock import patch

from django.core import signing
from rest_framework.test import APITestCase

from authn.models import Member
from event.tests.helpers import make_member
from mail.services.unsubscribe_token import (
    _SALT,
    build_oneclick_unsubscribe_token,
)


class OneClickUnsubscribeViewTests(APITestCase):
    def setUp(self):
        self.member = make_member(email="unsub@example.com")
        self.token = build_oneclick_unsubscribe_token(self.member)
        self.url = f"/mail/unsubscribe/{self.token}/"

    def test_valid_post_unsubscribes_member(self):
        self.assertTrue(self.member.email_subscribe)

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 200)
        self.member.refresh_from_db()
        self.assertFalse(self.member.email_subscribe)

    def test_idempotent_post(self):
        """Posting twice should succeed both times (RFC 8058 idempotency)."""
        self.client.post(self.url)
        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 200)
        self.member.refresh_from_db()
        self.assertFalse(self.member.email_subscribe)

    def test_get_unsubscribes_and_returns_html(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response["Content-Type"])
        self.member.refresh_from_db()
        self.assertFalse(self.member.email_subscribe)

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

    @patch("authn.services.email.send_notification_email")
    def test_sends_confirmation_email(self, mock_send):
        self.client.post(self.url)

        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        self.assertEqual(call_kwargs["recipient"], "unsub@example.com")
        self.assertIn("unsubscribed", call_kwargs["subject"].lower())

    @patch("authn.services.email.send_notification_email")
    def test_idempotent_post_does_not_resend_email(self, mock_send):
        """Second POST should not send another confirmation email."""
        self.client.post(self.url)
        mock_send.reset_mock()

        self.client.post(self.url)
        mock_send.assert_not_called()
