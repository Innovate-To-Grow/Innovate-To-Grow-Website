"""Inbox message actions: fetching one message (cached per account and folder) without ever marking it read."""

from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import TestCase

from apps.mail.services.inbox.reading.connection import (
    INBOX_LIST_CACHE_KEY,
    InboxError,
)
from apps.mail.services.inbox.reading.messages import fetch_inbox_message
from apps.mail.tests.services.inbox.mailbox.helpers import (
    _fake_message,
    _inbox_context,
    create_gmail_account,
)


class FetchInboxMessageTests(TestCase):
    def setUp(self):
        cache.clear()
        self.account = create_gmail_account()
        self.key = f"imap:{self.account.pk}"

    def tearDown(self):
        cache.clear()

    def test_fetch_returns_cached_when_present(self):
        cache.set(f"inbox:msg:{self.key}:INBOX:42", {"uid": "42", "subject": "cached"}, 1800)
        with patch("apps.mail.services.inbox._open_inbox", side_effect=AssertionError("IMAP was opened")):
            self.assertEqual(fetch_inbox_message("42")["subject"], "cached")

    def test_fetch_cache_isolated_per_folder(self):
        cache.set(f"inbox:msg:{self.key}:INBOX:42", {"uid": "42", "subject": "inbox-msg"}, 1800)
        cache.set(f"inbox:msg:{self.key}:SENT:42", {"uid": "42", "subject": "sent-msg"}, 1800)

        self.assertEqual(fetch_inbox_message("42")["subject"], "inbox-msg")
        self.assertEqual(fetch_inbox_message("42", folder="SENT")["subject"], "sent-msg")

    def test_fetch_returns_detailed_message_and_caches(self):
        client = Mock()
        client.fetch.return_value = [_fake_message()]

        with patch("apps.mail.services.inbox._open_inbox", return_value=_inbox_context(client)):
            result = fetch_inbox_message("42")

        self.assertEqual(result["uid"], "42")
        self.assertEqual((result["account"], result["account_address"]), (self.key, "i2g@gmail.com"))
        self.assertEqual(cache.get(f"inbox:msg:{self.key}:INBOX:42"), result)

    def test_opening_reads_with_peek_and_leaves_the_lists_unread(self):
        # A preview never marks the message read in Gmail (BODY.PEEK), so the cached lists keep it unread too.
        own_list = f"{INBOX_LIST_CACHE_KEY}:{self.key}:INBOX:30"
        cache.set(own_list, [{"uid": "42", "is_seen": False}], 300)
        client = Mock()
        client.fetch.return_value = [_fake_message(flags=())]

        with patch("apps.mail.services.inbox._open_inbox", return_value=_inbox_context(client)) as open_inbox:
            fetch_inbox_message("42", account=self.key)

        self.assertEqual(open_inbox.call_args.kwargs["account"].key, self.key)
        self.assertIs(client.fetch.call_args.kwargs["mark_seen"], False)
        self.assertFalse(cache.get(own_list)[0]["is_seen"])

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
