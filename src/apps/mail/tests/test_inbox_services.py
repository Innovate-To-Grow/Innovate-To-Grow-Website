"""Coverage for inbox service layer: connection, messages, formatting, reply."""

from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.cache import cache
from django.db.utils import OperationalError
from django.test import TestCase

from apps.core.models import AWSCredentialConfig, EmailServiceConfig, GmailAccessAccount
from apps.core.services.aws.credentials import AwsCredentialsError
from apps.mail.services.inbox.connection import (
    INBOX_LIST_CACHE_KEY,
    InboxError,
    _open_inbox,
    get_gmail_config,
    resolve_mailbox,
)
from apps.mail.services.inbox.formatting import (
    build_snippet,
    extract_from,
    extract_to,
    format_date,
)
from apps.mail.services.inbox.messages import (
    detailed_message,
    fetch_inbox_message,
    list_inbox_messages,
    message_summary,
    update_list_cache_seen,
)
from apps.mail.services.inbox.reply import (
    REPLY_SEND_FAILURE_MESSAGE,
    _build_reply_message,
    render_reply_html,
    send_reply,
)


@contextmanager
def _inbox_context(client):
    yield client


def _fake_message(**overrides):
    defaults = {
        "uid": "42",
        "subject": "Hi there",
        "from_values": SimpleNamespace(name="Alice", email="alice@example.com"),
        "from_": "alice@example.com",
        "to_values": [SimpleNamespace(name="Bob", email="bob@example.com")],
        "date": datetime(2026, 1, 1, 9, 30),
        "html": "<p>Hello <b>world</b></p>",
        "text": "Hello world",
        "flags": ("\\Seen",),
        "headers": {"message-id": ["<m@example.com>"], "references": ["<r@example.com>"]},
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class InboxFormattingTests(TestCase):
    def test_format_date_with_datetime(self):
        result = format_date(datetime(2026, 1, 2, 14, 5))
        self.assertEqual(result, "2026-01-02 02:05 PM")

    def test_format_date_with_string(self):
        self.assertEqual(format_date("Mon, 01 Jan 2026"), "Mon, 01 Jan 2026")

    def test_format_date_with_empty(self):
        self.assertEqual(format_date(None), "")

    def test_build_snippet_strips_html_and_truncates(self):
        long_html = "<p>" + ("word " * 100) + "</p>"
        snippet = build_snippet(SimpleNamespace(html=long_html, text=""))
        self.assertTrue(snippet.endswith("..."))
        self.assertLessEqual(len(snippet), 200)

    def test_build_snippet_returns_empty_when_no_body(self):
        self.assertEqual(build_snippet(SimpleNamespace(html="", text="")), "")

    def test_build_snippet_uses_text_when_no_html(self):
        snippet = build_snippet(SimpleNamespace(html="", text="Plain body"))
        self.assertEqual(snippet, "Plain body")

    def test_extract_from_uses_from_values(self):
        message = SimpleNamespace(from_values=SimpleNamespace(name="Alice", email="alice@example.com"))
        self.assertEqual(extract_from(message), ("Alice", "alice@example.com"))

    def test_extract_from_falls_back_to_from_attr(self):
        message = SimpleNamespace(from_values=None, from_="raw@example.com")
        self.assertEqual(extract_from(message), ("", "raw@example.com"))

    def test_extract_to_maps_recipients(self):
        message = SimpleNamespace(to_values=[SimpleNamespace(name="Bob", email="bob@example.com")])
        self.assertEqual(extract_to(message), [{"name": "Bob", "email": "bob@example.com"}])

    def test_extract_to_handles_missing_recipients(self):
        self.assertEqual(extract_to(SimpleNamespace(to_values=None)), [])


class InboxMessageMappingTests(TestCase):
    def test_message_summary_maps_fields(self):
        summary = message_summary(_fake_message())
        self.assertEqual(summary["uid"], "42")
        self.assertEqual(summary["subject"], "Hi there")
        self.assertEqual(summary["from_name"], "Alice")
        self.assertEqual(summary["from_email"], "alice@example.com")
        self.assertTrue(summary["is_seen"])
        self.assertIn("Hello world", summary["snippet"])

    def test_message_summary_defaults_subject_when_blank(self):
        summary = message_summary(_fake_message(subject="   ", flags=()))
        self.assertEqual(summary["subject"], "(No subject)")
        self.assertFalse(summary["is_seen"])

    def test_detailed_message_extracts_headers(self):
        detail = detailed_message(_fake_message())
        self.assertEqual(detail["message_id"], "<m@example.com>")
        self.assertEqual(detail["references"], "<r@example.com>")
        self.assertEqual(detail["to"], [{"name": "Bob", "email": "bob@example.com"}])
        self.assertEqual(detail["html"], "<p>Hello <b>world</b></p>")

    def test_detailed_message_handles_missing_headers(self):
        detail = detailed_message(_fake_message(headers={}, subject=""))
        self.assertEqual(detail["message_id"], "")
        self.assertEqual(detail["references"], "")
        self.assertEqual(detail["subject"], "(No subject)")


class ListInboxMessagesTests(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_list_returns_cached_when_present(self):
        cached = [{"uid": "99", "subject": "cached"}]
        cache.set(f"{INBOX_LIST_CACHE_KEY}:30", cached, 300)

        result = list_inbox_messages(limit=30)

        self.assertEqual(result, cached)

    def test_list_fetches_and_caches_messages(self):
        client = Mock()
        client.fetch.return_value = [_fake_message()]

        with patch("apps.mail.services.inbox._open_inbox", return_value=_inbox_context(client)):
            result = list_inbox_messages(limit=30, force_refresh=True)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["uid"], "42")
        self.assertEqual(cache.get(f"{INBOX_LIST_CACHE_KEY}:30"), result)

    def test_list_reraises_inbox_error(self):
        with patch("apps.mail.services.inbox._open_inbox", side_effect=InboxError("config")):
            with self.assertRaises(InboxError):
                list_inbox_messages(limit=30, force_refresh=True)

    def test_list_wraps_unexpected_error(self):
        with patch("apps.mail.services.inbox._open_inbox", side_effect=RuntimeError("boom")):
            with self.assertRaisesMessage(InboxError, "Failed to load inbox messages."):
                list_inbox_messages(limit=30, force_refresh=True)


class FetchInboxMessageTests(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_fetch_returns_cached_when_present(self):
        cache.set("inbox:msg:42", {"uid": "42", "subject": "cached"}, 1800)
        self.assertEqual(fetch_inbox_message("42")["subject"], "cached")

    def test_fetch_returns_detailed_message_and_caches(self):
        client = Mock()
        client.fetch.return_value = [_fake_message()]

        with patch("apps.mail.services.inbox._open_inbox", return_value=_inbox_context(client)):
            result = fetch_inbox_message("42")

        self.assertEqual(result["uid"], "42")
        self.assertEqual(cache.get("inbox:msg:42"), result)

    def test_fetch_raises_when_message_not_found(self):
        client = Mock()
        client.fetch.return_value = []

        with patch("apps.mail.services.inbox._open_inbox", return_value=_inbox_context(client)):
            with self.assertRaisesMessage(InboxError, "Message not found."):
                fetch_inbox_message("999")

    def test_fetch_wraps_unexpected_error(self):
        with patch("apps.mail.services.inbox._open_inbox", side_effect=RuntimeError("boom")):
            with self.assertRaisesMessage(InboxError, "Failed to fetch the message."):
                fetch_inbox_message("42")


class UpdateListCacheSeenTests(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_marks_matching_uid_seen(self):
        cache.set(f"{INBOX_LIST_CACHE_KEY}:30", [{"uid": "42", "is_seen": False}], 300)

        update_list_cache_seen("42")

        updated = cache.get(f"{INBOX_LIST_CACHE_KEY}:30")
        self.assertTrue(updated[0]["is_seen"])

    def test_skips_when_no_cache_for_limit(self):
        # No cache set; should not raise.
        update_list_cache_seen("42")
        self.assertIsNone(cache.get(f"{INBOX_LIST_CACHE_KEY}:30"))


class InboxConnectionTests(TestCase):
    def setUp(self):
        self.config = GmailAccessAccount.objects.create(
            name="Gmail",
            is_active=True,
            imap_host="imap.gmail.com",
            gmail_username="campaigns@ucmerced.edu",
            gmail_password="app-password",
        )

    def test_get_gmail_config_returns_configured_account(self):
        self.assertEqual(get_gmail_config().gmail_username, "campaigns@ucmerced.edu")

    def test_get_gmail_config_raises_on_db_error(self):
        with patch(
            "apps.mail.services.inbox.connection.GmailAccessAccount.load",
            side_effect=OperationalError("no such table"),
        ):
            with self.assertRaisesMessage(InboxError, "Gmail configuration is unavailable"):
                get_gmail_config()

    def test_get_gmail_config_raises_when_not_configured(self):
        with patch(
            "apps.mail.services.inbox.connection.GmailAccessAccount.load",
            return_value=SimpleNamespace(is_configured=False),
        ):
            with self.assertRaisesMessage(InboxError, "No active Gmail import account is configured."):
                get_gmail_config()

    def test_resolve_mailbox_delegates_to_gmail_resolver(self):
        with patch(
            "apps.mail.services.gmail_import.resolve_gmail_mailbox", return_value="resolved@example.com"
        ) as mock_resolve:
            self.assertEqual(resolve_mailbox("requested@example.com"), "resolved@example.com")
        mock_resolve.assert_called_once_with("requested@example.com")

    def test_open_inbox_yields_logged_in_client(self):
        login_context = Mock()
        login_client = Mock()
        login_context.__enter__ = Mock(return_value=login_client)
        login_context.__exit__ = Mock(return_value=False)
        mailbox_client = Mock()
        mailbox_client.login.return_value = login_context

        with (
            patch("apps.mail.services.inbox.connection.resolve_mailbox", return_value="campaigns@ucmerced.edu"),
            patch("apps.mail.services.inbox.connection.MailBox", return_value=mailbox_client) as mock_mailbox,
        ):
            with _open_inbox() as client:
                self.assertIs(client, login_client)

        mock_mailbox.assert_called_once_with("imap.gmail.com")
        mailbox_client.login.assert_called_once_with("campaigns@ucmerced.edu", "app-password", initial_folder="INBOX")

    def test_open_inbox_wraps_connection_failure(self):
        with (
            patch("apps.mail.services.inbox.connection.resolve_mailbox", return_value="campaigns@ucmerced.edu"),
            patch("apps.mail.services.inbox.connection.MailBox", side_effect=RuntimeError("no connection")),
        ):
            with self.assertRaisesMessage(InboxError, "Unable to connect to inbox for campaigns@ucmerced.edu."):
                with _open_inbox():
                    pass

    def test_open_inbox_reraises_inbox_error_from_body(self):
        login_context = Mock()
        login_client = Mock()
        login_context.__enter__ = Mock(return_value=login_client)
        login_context.__exit__ = Mock(return_value=False)
        mailbox_client = Mock()
        mailbox_client.login.return_value = login_context

        with (
            patch("apps.mail.services.inbox.connection.resolve_mailbox", return_value="campaigns@ucmerced.edu"),
            patch("apps.mail.services.inbox.connection.MailBox", return_value=mailbox_client),
        ):
            # An InboxError raised inside the with-body must propagate unchanged,
            # not be re-wrapped as a connection failure.
            with self.assertRaisesMessage(InboxError, "downstream failure"):
                with _open_inbox():
                    raise InboxError("downstream failure")


class ReplyRenderTests(TestCase):
    def test_render_reply_html_linkifies_urls(self):
        html = render_reply_html("Visit https://example.com now", quoted_text="prior text")
        self.assertIn('<a href="https://example.com"', html)
        self.assertIn("prior text", html)

    def test_build_reply_message_sets_threading_headers(self):
        config = SimpleNamespace(source_address="I2G <reply@example.com>")
        message = _build_reply_message(
            config=config,
            to_email="alice@example.com",
            subject="Re: Hi",
            html="<p>Hi</p>",
            cc_list=["cc@example.com"],
            in_reply_to="<orig@example.com>",
            references="<a@example.com> <b@example.com>",
        )

        self.assertEqual(message["In-Reply-To"], "<orig@example.com>")
        self.assertEqual(message["References"], "<a@example.com> <b@example.com>")
        self.assertEqual(message["Cc"], "cc@example.com")


class SendReplyTests(TestCase):
    def setUp(self):
        self.email_config = EmailServiceConfig.objects.create(
            name="Mail",
            is_active=True,
            ses_from_email="reply@example.com",
            ses_from_name="I2G",
        )

    def test_send_reply_returns_empty_on_success(self):
        AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="AKID",
            secret_access_key="SECRET",
            default_region="us-west-2",
        )
        with patch("boto3.client") as mock_client:
            error = send_reply(
                to_email="alice@example.com",
                subject="Re: Hi",
                reply_body="Hello",
                cc_email="cc@example.com",
            )

        self.assertEqual(error, "")
        mock_client.return_value.send_raw_email.assert_called_once()
        call_kwargs = mock_client.return_value.send_raw_email.call_args.kwargs
        self.assertEqual(call_kwargs["Destinations"], ["alice@example.com", "cc@example.com"])

    def test_send_reply_returns_message_when_aws_credentials_missing(self):
        AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="AKID",
            secret_access_key="SECRET",
            default_region="us-west-2",
        )
        with patch(
            "apps.mail.services.inbox.reply.resolve_aws_credentials",
            side_effect=AwsCredentialsError("missing"),
        ):
            error = send_reply(to_email="alice@example.com", subject="Re: Hi", reply_body="Hi")

        self.assertEqual(error, "AWS IAM is not configured. Cannot send reply.")

    def test_send_reply_returns_failure_message_on_unexpected_error(self):
        AWSCredentialConfig.objects.create(
            name="AWS",
            is_active=True,
            access_key_id="AKID",
            secret_access_key="SECRET",
            default_region="us-west-2",
        )
        with patch("boto3.client") as mock_client:
            mock_client.return_value.send_raw_email.side_effect = RuntimeError("SES down")
            error = send_reply(to_email="alice@example.com", subject="Re: Hi", reply_body="Hi")

        self.assertEqual(error, REPLY_SEND_FAILURE_MESSAGE)
