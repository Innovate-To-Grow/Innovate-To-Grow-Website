"""Coverage for inbox admin reply/detail/list views and helpers."""

from unittest.mock import patch

from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.core.models import EmailServiceConfig
from apps.event.tests.helpers import make_superuser
from apps.mail.admin.inbox.helpers import (
    build_original_from,
    build_reply_references,
    build_reply_subject,
    message_body_html,
    parse_folder,
    parse_limit,
)
from apps.mail.services.inbox import InboxError


def _message(**overrides):
    msg = {
        "uid": "42",
        "from_name": "Alice Sender",
        "from_email": "alice@example.com",
        "to": [],
        "cc": [],
        "subject": "Project update",
        "snippet": "Body",
        "date": "Mon, 01 Jan 2026 00:00:00 +0000",
        "is_seen": True,
        "html": "<p>Hello</p>",
        "text": "Hello",
        "message_id": "<msg@example.com>",
        "references": "<prev@example.com>",
    }
    msg.update(overrides)
    return msg


class InboxHelperTests(TestCase):
    def test_parse_limit_returns_default_for_invalid(self):
        request = RequestFactory().get("/?limit=notanumber")
        self.assertEqual(parse_limit(request), 30)

    def test_parse_limit_returns_default_for_unlisted_value(self):
        request = RequestFactory().get("/?limit=9999")
        self.assertEqual(parse_limit(request), 30)

    def test_parse_limit_accepts_allowed_choice(self):
        from apps.mail.services.inbox import INBOX_LIMIT_CHOICES

        allowed = INBOX_LIMIT_CHOICES[0]
        request = RequestFactory().get(f"/?limit={allowed}")
        self.assertEqual(parse_limit(request), allowed)

    def test_parse_folder_defaults_to_inbox(self):
        request = RequestFactory().get("/")
        self.assertEqual(parse_folder(request), "INBOX")

    def test_parse_folder_accepts_sent_case_insensitive(self):
        request = RequestFactory().get("/?folder=sent")
        self.assertEqual(parse_folder(request), "SENT")

    def test_parse_folder_rejects_unknown_value(self):
        request = RequestFactory().get("/?folder=trash")
        self.assertEqual(parse_folder(request), "INBOX")

    def test_message_body_html_uses_html_when_present(self):
        self.assertEqual(message_body_html(_message(html="<b>Hi</b>")), "<b>Hi</b>")

    def test_message_body_html_escapes_text_fallback(self):
        result = message_body_html(_message(html="", text="<script>x</script>"))
        self.assertEqual(result, "<pre>&lt;script&gt;x&lt;/script&gt;</pre>")

    def test_build_reply_references_appends_message_id(self):
        result = build_reply_references(_message(references="<a>", message_id="<b>"))
        self.assertEqual(result, "<a> <b>")

    def test_build_reply_references_message_id_only(self):
        result = build_reply_references(_message(references="", message_id="<b>"))
        self.assertEqual(result, "<b>")

    def test_build_reply_references_falls_back_to_references(self):
        result = build_reply_references(_message(references="<a>", message_id=""))
        self.assertEqual(result, "<a>")

    def test_build_original_from_with_name(self):
        result = build_original_from(_message(from_name="Bob", from_email="bob@example.com"))
        self.assertEqual(result, "Bob <bob@example.com>")

    def test_build_original_from_without_name(self):
        result = build_original_from(_message(from_name="", from_email="bob@example.com"))
        self.assertEqual(result, "bob@example.com")

    def test_build_reply_subject_prefixes_re(self):
        self.assertEqual(build_reply_subject("Hello"), "Re: Hello")

    def test_build_reply_subject_keeps_existing_re(self):
        self.assertEqual(build_reply_subject("RE: Hello"), "RE: Hello")


class InboxReplyViewTests(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        EmailServiceConfig.objects.create(
            name="Mail",
            is_active=True,
            ses_from_email="reply@example.com",
            ses_from_name="I2G",
        )

    @patch("apps.mail.admin.inbox.fetch_inbox_message")
    def test_reply_view_get_renders_compose_form(self, mock_fetch):
        mock_fetch.return_value = _message()

        response = self.client.get(reverse("admin:mail_inbox_reply", args=["42"]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Re: Project update")
        self.assertContains(response, "reply@example.com")

    @patch("apps.mail.admin.inbox.fetch_inbox_message", side_effect=InboxError("nope"))
    def test_reply_view_redirects_on_inbox_error(self, mock_fetch):
        response = self.client.get(reverse("admin:mail_inbox_reply", args=["42"]), follow=True)

        self.assertRedirects(response, reverse("admin:mail_inbox_list"))
        self.assertContains(response, "Message could not be loaded")

    @patch("apps.mail.admin.inbox.fetch_inbox_message")
    def test_reply_view_post_empty_body_errors(self, mock_fetch):
        mock_fetch.return_value = _message()

        response = self.client.post(
            reverse("admin:mail_inbox_reply", args=["42"]),
            {"reply_body": "   "},
            follow=True,
        )

        self.assertContains(response, "Reply body cannot be empty")

    @patch("apps.mail.admin.inbox.send_reply")
    @patch("apps.mail.admin.inbox.fetch_inbox_message")
    def test_reply_view_post_send_error_redirects_back(self, mock_fetch, mock_send):
        mock_fetch.return_value = _message()
        mock_send.return_value = "SES exploded"

        response = self.client.post(
            reverse("admin:mail_inbox_reply", args=["42"]),
            {"reply_body": "Hello there", "to_email": "alice@example.com"},
            follow=True,
        )

        self.assertContains(response, "SES exploded")
        mock_send.assert_called_once()

    @patch("apps.mail.admin.inbox.send_reply")
    @patch("apps.mail.admin.inbox.fetch_inbox_message")
    def test_reply_view_post_success_redirects_to_detail(self, mock_fetch, mock_send):
        mock_fetch.return_value = _message()
        mock_send.return_value = None

        response = self.client.post(
            reverse("admin:mail_inbox_reply", args=["42"]),
            {
                "reply_body": "Hello there",
                "subject": "Re: Project update",
                "to_email": "alice@example.com",
                "cc_email": "boss@example.com",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("admin:mail_inbox_detail", args=["42"]))
        kwargs = mock_send.call_args.kwargs
        self.assertEqual(kwargs["to_email"], "alice@example.com")
        self.assertEqual(kwargs["cc_email"], "boss@example.com")
        self.assertEqual(kwargs["in_reply_to"], "<msg@example.com>")


class InboxReplyFragmentViewTests(TestCase):
    def setUp(self):
        self.admin_user = make_superuser()
        self.client.login(username="admin@example.com", password="testpass123")
        EmailServiceConfig.objects.create(
            name="Mail",
            is_active=True,
            ses_from_email="reply@example.com",
            ses_from_name="I2G",
        )

    @patch("apps.mail.admin.inbox.fetch_inbox_message")
    def test_fragment_get_returns_form_html(self, mock_fetch):
        mock_fetch.return_value = _message()

        response = self.client.get(reverse("admin:mail_inbox_reply_fragment", args=["42"]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Re: Project update")

    @patch("apps.mail.admin.inbox.fetch_inbox_message", side_effect=InboxError("nope"))
    def test_fragment_get_inbox_error_returns_html_error(self, mock_fetch):
        response = self.client.get(reverse("admin:mail_inbox_reply_fragment", args=["42"]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Message could not be loaded")

    @patch("apps.mail.admin.inbox.fetch_inbox_message", side_effect=RuntimeError("boom"))
    def test_fragment_get_unexpected_error_returns_html_error(self, mock_fetch):
        response = self.client.get(reverse("admin:mail_inbox_reply_fragment", args=["42"]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Message could not be loaded")

    @patch("apps.mail.admin.inbox.fetch_inbox_message", side_effect=RuntimeError("boom"))
    def test_fragment_post_unexpected_error_returns_json_error(self, mock_fetch):
        response = self.client.post(reverse("admin:mail_inbox_reply_fragment", args=["42"]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "Message could not be loaded. Check server logs.")

    @patch("apps.mail.admin.inbox.fetch_inbox_message")
    def test_fragment_post_empty_body_json_error(self, mock_fetch):
        mock_fetch.return_value = _message()

        response = self.client.post(
            reverse("admin:mail_inbox_reply_fragment", args=["42"]),
            {"reply_body": ""},
        )

        self.assertEqual(response.json(), {"ok": False, "error": "Reply body cannot be empty."})

    @patch("apps.mail.admin.inbox.send_reply")
    @patch("apps.mail.admin.inbox.fetch_inbox_message")
    def test_fragment_post_send_error_json(self, mock_fetch, mock_send):
        mock_fetch.return_value = _message()
        mock_send.return_value = "delivery failed"

        response = self.client.post(
            reverse("admin:mail_inbox_reply_fragment", args=["42"]),
            {"reply_body": "Hi"},
        )

        self.assertEqual(response.json(), {"ok": False, "error": "delivery failed"})

    @patch("apps.mail.admin.inbox.send_reply")
    @patch("apps.mail.admin.inbox.fetch_inbox_message")
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

    @patch("apps.mail.admin.inbox.send_reply")
    @patch("apps.mail.admin.inbox.fetch_inbox_message")
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

    @patch("apps.mail.admin.inbox.fetch_inbox_message", side_effect=InboxError("nope"))
    def test_detail_view_inbox_error_redirects(self, mock_fetch):
        response = self.client.get(reverse("admin:mail_inbox_detail", args=["42"]), follow=True)

        self.assertRedirects(response, reverse("admin:mail_inbox_list"))
        self.assertContains(response, "Message could not be loaded")

    @patch("apps.mail.admin.inbox.fetch_inbox_message", side_effect=RuntimeError("boom"))
    def test_detail_view_unexpected_error_redirects(self, mock_fetch):
        response = self.client.get(reverse("admin:mail_inbox_detail", args=["42"]), follow=True)

        self.assertRedirects(response, reverse("admin:mail_inbox_list"))
        self.assertContains(response, "Message could not be loaded")

    @patch("apps.mail.admin.inbox.fetch_inbox_message", side_effect=InboxError("nope"))
    def test_detail_fragment_inbox_error_returns_html(self, mock_fetch):
        response = self.client.get(reverse("admin:mail_inbox_detail_fragment", args=["42"]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Message could not be loaded")

    @patch("apps.mail.admin.inbox.fetch_inbox_message", side_effect=RuntimeError("boom"))
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

    @patch("apps.mail.admin.inbox.list_inbox_messages", side_effect=InboxError("config"))
    def test_fragment_inbox_error_shows_config_message(self, mock_list):
        response = self.client.get(reverse("admin:mail_inbox_fragment"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Check Gmail import configuration")

    @patch("apps.mail.admin.inbox.list_inbox_messages", side_effect=RuntimeError("boom"))
    def test_fragment_unexpected_error_shows_server_logs_message(self, mock_list):
        response = self.client.get(reverse("admin:mail_inbox_fragment"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Check server logs")
