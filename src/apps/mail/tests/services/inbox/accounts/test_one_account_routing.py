"""``list_inbox_messages`` / ``fetch_inbox_message`` with an account key read that one account only."""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from apps.mail.services.inbox.reading.accounts import ACCOUNT_UNAVAILABLE_MESSAGE
from apps.mail.services.inbox.reading.connection import (
    INBOX_MSG_CACHE_PREFIX,
    InboxError,
)
from apps.mail.services.inbox.reading.listing import list_inbox_messages
from apps.mail.services.inbox.reading.messages import fetch_inbox_message
from apps.mail.tests.services.delivery.graph_inbox.helpers import (
    MAILBOX,
    MESSAGE_ID,
    RAW_MIME,
    graph_config,
)
from apps.mail.tests.services.inbox.accounts.helpers import (
    FETCH_TARGET,
    GRAPH_KEY,
    GRAPH_MESSAGES,
    LIST_TARGET,
    UniversalInboxMixin,
    gmail_account,
    imap_message,
)


class OneAccountRoutingTests(UniversalInboxMixin, TestCase):
    def setUp(self):
        super().setUp()
        graph_config()
        self.gmail = gmail_account()
        self.imap_key = f"imap:{self.gmail.pk}"

    def test_list_with_an_imap_key_reads_that_account_only(self):
        self.imap.answer(self.imap_key, [imap_message("21", 21)])

        with patch(LIST_TARGET) as graph_list:
            results = list_inbox_messages(limit=30, account=self.imap_key)

        graph_list.assert_not_called()
        self.assertEqual(self.open_inbox.call_args.kwargs["account"].key, self.imap_key)
        self.assertEqual([(item["uid"], item["account"]) for item in results], [("21", self.imap_key)])

    def test_list_without_a_key_reads_the_default_account(self):
        with patch(LIST_TARGET, autospec=True, return_value=GRAPH_MESSAGES):
            results = list_inbox_messages(limit=30)

        self.open_inbox.assert_not_called()
        self.assertEqual({item["account"] for item in results}, {GRAPH_KEY})

    def test_fetch_with_an_imap_key_opens_that_account(self):
        self.imap.answer(self.imap_key, [imap_message("42", 21)])

        with patch(FETCH_TARGET) as graph_fetch:
            detail = fetch_inbox_message("42", account=self.imap_key)

        graph_fetch.assert_not_called()
        self.assertEqual((detail["uid"], detail["account"]), ("42", self.imap_key))
        self.assertEqual(cache.get(f"{INBOX_MSG_CACHE_PREFIX}{self.imap_key}:INBOX:42"), detail)

    def test_fetch_with_a_graph_key_reads_that_mailbox(self):
        with patch(FETCH_TARGET, autospec=True, return_value=RAW_MIME) as graph_fetch:
            detail = fetch_inbox_message(MESSAGE_ID, account=GRAPH_KEY)

        self.open_inbox.assert_not_called()
        self.assertEqual(graph_fetch.call_args.args[0].mailbox, MAILBOX)
        self.assertEqual((detail["account"], detail["account_address"]), (GRAPH_KEY, MAILBOX))

    def test_the_same_uid_is_cached_per_account(self):
        cache.set(f"{INBOX_MSG_CACHE_PREFIX}{GRAPH_KEY}:INBOX:42", {"uid": "42", "subject": "graph"})
        cache.set(f"{INBOX_MSG_CACHE_PREFIX}{self.imap_key}:INBOX:42", {"uid": "42", "subject": "imap"})

        self.assertEqual(fetch_inbox_message("42", account=GRAPH_KEY)["subject"], "graph")
        self.assertEqual(fetch_inbox_message("42", account=self.imap_key)["subject"], "imap")

    def test_an_unknown_key_reads_nothing(self):
        with patch(LIST_TARGET) as graph_list, patch(FETCH_TARGET) as graph_fetch:
            for key in ("bogus", "imap:999999", "graph:other@contoso.com"):
                with self.subTest(key=key):
                    with self.assertRaisesMessage(InboxError, ACCOUNT_UNAVAILABLE_MESSAGE):
                        list_inbox_messages(account=key)
                    with self.assertRaisesMessage(InboxError, ACCOUNT_UNAVAILABLE_MESSAGE):
                        fetch_inbox_message("42", account=key)

        graph_list.assert_not_called()
        graph_fetch.assert_not_called()
        self.open_inbox.assert_not_called()
