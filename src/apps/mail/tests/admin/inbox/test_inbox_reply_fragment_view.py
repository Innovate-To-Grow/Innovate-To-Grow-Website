from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.core.models import EmailServiceConfig
from apps.event.tests.helpers import make_superuser
from apps.mail.services.inbox import InboxError
from apps.mail.tests.admin.inbox.test_inbox_views import _message


class InboxReplyFragmentViewTests(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        EmailServiceConfig.objects.create(
            name="Mail",
            is_active=True,
            from_email="reply@example.com",
            from_name="I2G",
        )

    @patch("apps.mail.admin.inbox.services.fetch_inbox_message")
    def test_fragment_get_returns_form_html(self, mock_fetch):
        mock_fetch.return_value = _message()

        response = self.client.get(reverse("admin:mail_inbox_reply_fragment", args=["42"]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Re: Project update")

    @patch("apps.mail.admin.inbox.services.fetch_inbox_message", side_effect=InboxError("nope"))
    def test_fragment_get_inbox_error_returns_html_error(self, mock_fetch):
        response = self.client.get(reverse("admin:mail_inbox_reply_fragment", args=["42"]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Message could not be loaded")

    @patch("apps.mail.admin.inbox.services.fetch_inbox_message", side_effect=RuntimeError("boom"))
    def test_fragment_get_unexpected_error_returns_html_error(self, mock_fetch):
        response = self.client.get(reverse("admin:mail_inbox_reply_fragment", args=["42"]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Message could not be loaded")

    @patch("apps.mail.admin.inbox.services.fetch_inbox_message", side_effect=RuntimeError("boom"))
    def test_fragment_post_unexpected_error_returns_json_error(self, mock_fetch):
        response = self.client.post(reverse("admin:mail_inbox_reply_fragment", args=["42"]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "Message could not be loaded. Check server logs.")

    @patch("apps.mail.admin.inbox.services.fetch_inbox_message")
    def test_fragment_post_empty_body_json_error(self, mock_fetch):
        mock_fetch.return_value = _message()

        response = self.client.post(
            reverse("admin:mail_inbox_reply_fragment", args=["42"]),
            {"reply_body": ""},
        )

        self.assertEqual(response.json(), {"ok": False, "error": "Reply body cannot be empty."})

    @patch("apps.mail.admin.inbox.services.send_reply")
    @patch("apps.mail.admin.inbox.services.fetch_inbox_message")
    def test_fragment_post_send_error_json(self, mock_fetch, mock_send):
        mock_fetch.return_value = _message()
        mock_send.return_value = "delivery failed"

        response = self.client.post(
            reverse("admin:mail_inbox_reply_fragment", args=["42"]),
            {"reply_body": "Hi"},
        )

        self.assertEqual(response.json(), {"ok": False, "error": "delivery failed"})

    @patch("apps.mail.admin.inbox.services.send_reply")
    @patch("apps.mail.admin.inbox.services.fetch_inbox_message")
    def test_fragment_post_success_json_includes_cc(self, mock_fetch, mock_send):
        mock_fetch.return_value = _message()
        mock_send.return_value = None

        response = self.client.post(
            reverse("admin:mail_inbox_reply_fragment", args=["42"]),
            {"reply_body": "Hi", "to_email": "alice@example.com", "cc_email": "cc@example.com"},
        )

        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["message"], "Reply sent to alice@example.com (Cc: cc@example.com).")

    @patch("apps.mail.admin.inbox.services.send_reply")
    @patch("apps.mail.admin.inbox.services.fetch_inbox_message")
    def test_fragment_post_success_json_without_cc(self, mock_fetch, mock_send):
        mock_fetch.return_value = _message()
        mock_send.return_value = None

        response = self.client.post(
            reverse("admin:mail_inbox_reply_fragment", args=["42"]),
            {"reply_body": "Hi", "to_email": "alice@example.com"},
        )

        self.assertEqual(response.json()["message"], "Reply sent to alice@example.com.")


class InboxDetailViewErrorTests(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")

    @patch("apps.mail.admin.inbox.services.fetch_inbox_message", side_effect=InboxError("nope"))
    def test_detail_view_inbox_error_redirects(self, mock_fetch):
        response = self.client.get(reverse("admin:mail_inbox_detail", args=["42"]), follow=True)

        self.assertRedirects(response, reverse("admin:mail_inbox_list"))
        self.assertContains(response, "Message could not be loaded")

    @patch("apps.mail.admin.inbox.services.fetch_inbox_message", side_effect=RuntimeError("boom"))
    def test_detail_view_unexpected_error_redirects(self, mock_fetch):
        response = self.client.get(reverse("admin:mail_inbox_detail", args=["42"]), follow=True)

        self.assertRedirects(response, reverse("admin:mail_inbox_list"))
        self.assertContains(response, "Message could not be loaded")

    @patch("apps.mail.admin.inbox.services.fetch_inbox_message", side_effect=InboxError("nope"))
    def test_detail_fragment_inbox_error_returns_html(self, mock_fetch):
        response = self.client.get(reverse("admin:mail_inbox_detail_fragment", args=["42"]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Message could not be loaded")

    @patch("apps.mail.admin.inbox.services.fetch_inbox_message", side_effect=RuntimeError("boom"))
    def test_detail_fragment_unexpected_error_returns_html(self, mock_fetch):
        response = self.client.get(reverse("admin:mail_inbox_detail_fragment", args=["42"]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Message could not be loaded")


class InboxListViewTests(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")

    def test_list_view_renders_shell(self):
        response = self.client.get(reverse("admin:mail_inbox_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Inbox")

    @patch("apps.mail.admin.inbox.services.list_inbox_messages", side_effect=InboxError("config"))
    def test_fragment_inbox_error_shows_config_message(self, mock_list):
        response = self.client.get(reverse("admin:mail_inbox_fragment"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Check the Microsoft Graph mailbox scope or the Gmail import configuration")

    @patch("apps.mail.admin.inbox.services.list_inbox_messages", side_effect=RuntimeError("boom"))
    def test_fragment_unexpected_error_shows_server_logs_message(self, mock_list):
        response = self.client.get(reverse("admin:mail_inbox_fragment"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Check server logs")
