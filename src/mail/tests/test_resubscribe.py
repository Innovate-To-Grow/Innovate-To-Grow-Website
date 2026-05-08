from unittest.mock import patch

from rest_framework.test import APITestCase

from authn.models import ContactEmail
from event.tests.helpers import make_member
from mail.services.unsubscribe_token import build_resubscribe_token


class ResubscribeViewTests(APITestCase):
    def setUp(self):
        self.member = make_member(email="resub@example.com")
        self.primary_email = ContactEmail.objects.get(member=self.member, email_type="primary")
        self.primary_email.subscribe = False
        self.primary_email.save(update_fields=["subscribe"])
        self.token = build_resubscribe_token(self.member)
        self.url = f"/mail/resubscribe/{self.token}/"

    def _is_subscribed(self):
        self.primary_email.refresh_from_db()
        return self.primary_email.subscribe

    def test_valid_post_resubscribes_member(self):
        self.assertFalse(self._is_subscribed())
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response["Content-Type"])
        self.assertTrue(self._is_subscribed())

    def test_invalid_token_returns_400(self):
        response = self.client.post("/mail/resubscribe/garbage-token/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("text/html", response["Content-Type"])

    def test_get_not_allowed(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    @patch("authn.services.email.send_notification_email")
    def test_sends_confirmation_email(self, mock_send):
        self.client.post(self.url)
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        self.assertEqual(call_kwargs["recipient"], "resub@example.com")
        self.assertIn("resubscribed", call_kwargs["subject"].lower())

    def test_already_subscribed_no_error(self):
        self.primary_email.subscribe = True
        self.primary_email.save(update_fields=["subscribe"])
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 200)
