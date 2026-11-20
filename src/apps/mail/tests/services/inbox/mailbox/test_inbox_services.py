"""Coverage for inbox service layer: connection, messages, formatting, reply."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import TestCase

from apps.mail.services.inbox.reading.connection import (
    INBOX_LIST_CACHE_KEY,
    InboxError,
)
from apps.mail.services.inbox.reading.formatting import (
    build_snippet,
    extract_from,
    extract_to,
    format_date,
    timestamp_of,
)
from apps.mail.services.inbox.reading.listing import list_inbox_messages
from apps.mail.services.inbox.reading.messages import detailed_message, message_summary
from apps.mail.tests.services.inbox.mailbox.helpers import (
    _fake_message,
    _inbox_context,
    create_gmail_account,
)


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

    def test_timestamp_of_a_datetime(self):
        moment = datetime(2026, 1, 2, 14, 5)
        self.assertEqual(timestamp_of(moment), moment.timestamp())

    def test_timestamp_of_anything_else_is_zero(self):
        for value in (None, "", "Mon, 01 Jan 2026"):
            with self.subTest(value=value):
                self.assertEqual(timestamp_of(value), 0.0)

    def test_timestamp_of_an_unrepresentable_datetime_is_zero(self):
        class Unrepresentable(datetime):
            def timestamp(self):
                raise OverflowError("out of range")

        self.assertEqual(timestamp_of(Unrepresentable(2026, 1, 1)), 0.0)


class InboxMessageMappingTests(TestCase):
    def test_message_summary_maps_fields(self):
        summary = message_summary(_fake_message())
        self.assertEqual(summary["uid"], "42")
        self.assertEqual(summary["subject"], "Hi there")
        self.assertEqual(summary["from_name"], "Alice")
        self.assertEqual(summary["from_email"], "alice@example.com")
        self.assertEqual(summary["to"], [{"name": "Bob", "email": "bob@example.com"}])
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
        self.assertEqual(detail["reply_to"], "")
        self.assertEqual(detail["return_path"], "")
        self.assertEqual(detail["authentication_results"], "")

    def test_detailed_message_extracts_auth_headers(self):
        detail = detailed_message(
            _fake_message(
                headers={
                    "reply-to": ["Support <reply@evil.com>"],
                    "return-path": ["<bounce@evil.com>"],
                    "authentication-results": ["mx.google.com; spf=fail; dmarc=fail"],
                }
            )
        )
        self.assertEqual(detail["reply_to"], "reply@evil.com")
        self.assertEqual(detail["return_path"], "bounce@evil.com")
        self.assertIn("dmarc=fail", detail["authentication_results"])


class ListInboxMessagesTests(TestCase):
    def setUp(self):
        cache.clear()
        self.account = create_gmail_account()
        self.key = f"imap:{self.account.pk}"

    def tearDown(self):
        cache.clear()

    def test_list_returns_cached_when_present(self):
        cached = [{"uid": "99", "subject": "cached"}]
        cache.set(f"{INBOX_LIST_CACHE_KEY}:{self.key}:INBOX:30", cached, 300)

        with patch("apps.mail.services.inbox._open_inbox", side_effect=AssertionError("IMAP was opened")):
            result = list_inbox_messages(limit=30)

        self.assertEqual(result, cached)

    def test_list_cache_isolated_per_folder(self):
        cache.set(f"{INBOX_LIST_CACHE_KEY}:{self.key}:INBOX:30", [{"uid": "1", "subject": "inbox"}], 300)
        cache.set(f"{INBOX_LIST_CACHE_KEY}:{self.key}:SENT:30", [{"uid": "1", "subject": "sent"}], 300)

        self.assertEqual(list_inbox_messages(limit=30)[0]["subject"], "inbox")
        self.assertEqual(list_inbox_messages(limit=30, folder="SENT")[0]["subject"], "sent")

    def test_list_fetches_and_caches_messages(self):
        client = Mock()
        client.fetch.return_value = [_fake_message()]

        with patch("apps.mail.services.inbox._open_inbox", return_value=_inbox_context(client)):
            result = list_inbox_messages(limit=30, force_refresh=True)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["uid"], "42")
        self.assertEqual((result[0]["account"], result[0]["account_address"]), (self.key, "i2g@gmail.com"))
        self.assertEqual(result[0]["timestamp"], datetime(2026, 1, 1, 9, 30).timestamp())
        self.assertEqual(cache.get(f"{INBOX_LIST_CACHE_KEY}:{self.key}:INBOX:30"), result)

    def test_list_reraises_inbox_error(self):
        with patch("apps.mail.services.inbox._open_inbox", side_effect=InboxError("config")):
            with self.assertRaisesMessage(InboxError, "config"):
                list_inbox_messages(limit=30, force_refresh=True)

    def test_list_wraps_unexpected_error(self):
        with patch("apps.mail.services.inbox._open_inbox", side_effect=RuntimeError("boom")):
            with self.assertRaisesMessage(InboxError, "Failed to load inbox messages."):
                list_inbox_messages(limit=30, force_refresh=True)
