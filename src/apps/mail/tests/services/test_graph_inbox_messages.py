"""Inbox list/fetch routing: Microsoft Graph when read is granted on the I2G mailbox, Gmail IMAP otherwise."""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.db.utils import OperationalError, ProgrammingError
from django.test import TestCase

from apps.core.models import EmailServiceConfig, GmailAccessAccount, MicrosoftGraphProviderConfig
from apps.core.services.email.graph import auth
from apps.core.services.email.graph.mailbox import GraphMailboxReader, GraphReadError
from apps.core.services.email.graph.transport import HttpResponse
from apps.mail.admin.inbox.list_views import _inbox_account
from apps.mail.services.inbox.connection import INBOX_LIST_CACHE_KEY, INBOX_MSG_CACHE_PREFIX, InboxError
from apps.mail.services.inbox.messages import fetch_inbox_message, list_inbox_messages
from apps.mail.tests.services.test_graph_inbox_backend import (
    GRAPH_MESSAGE,
    MAILBOX,
    MESSAGE_ID,
    RAW_MIME,
    SUMMARY_KEYS,
    Permission,
    graph_config,
)

LIST_TARGET = "apps.core.services.email.graph.mailbox.GraphMailboxReader.list_messages"
FETCH_TARGET = "apps.core.services.email.graph.mailbox.GraphMailboxReader.fetch_mime"
OPEN_INBOX = "apps.mail.services.inbox._open_inbox"


class GraphInboxFixtureMixin:
    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)
        EmailServiceConfig.objects.all().delete()
        MicrosoftGraphProviderConfig.objects.all().delete()
        EmailServiceConfig.objects.create(name="Prod", is_active=True, provider="graph", from_email=MAILBOX)
        # Gmail IMAP must never be opened while Graph serves the inbox.
        patcher = patch(OPEN_INBOX, side_effect=AssertionError("IMAP was opened"))
        self.open_inbox = patcher.start()
        self.addCleanup(patcher.stop)


class GraphInboxRoutingTests(GraphInboxFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        graph_config()

    @patch(LIST_TARGET, autospec=True, return_value=[GRAPH_MESSAGE])
    def test_list_reads_through_graph_and_caches_under_a_graph_key(self, list_messages):
        results = list_inbox_messages(limit=30, folder="INBOX")

        self.assertEqual([set(item) for item in results], [SUMMARY_KEYS])
        self.assertEqual(results[0]["uid"], MESSAGE_ID)
        reader, folder, limit = list_messages.call_args.args
        self.assertIsInstance(reader, GraphMailboxReader)
        self.assertEqual((reader.mailbox, folder, limit), (MAILBOX, "INBOX", 30))
        self.assertEqual(cache.get(f"{INBOX_LIST_CACHE_KEY}:graph:INBOX:30"), results)
        self.assertIsNone(cache.get(f"{INBOX_LIST_CACHE_KEY}:INBOX:30"))
        self.open_inbox.assert_not_called()

    @patch(LIST_TARGET, autospec=True, return_value=[GRAPH_MESSAGE])
    def test_list_cache_miss_then_hit_and_force_refresh(self, list_messages):
        first = list_inbox_messages(limit=10)
        second = list_inbox_messages(limit=10)
        self.assertEqual(first, second)
        self.assertEqual(list_messages.call_count, 1)

        list_inbox_messages(limit=10, force_refresh=True)

        self.assertEqual(list_messages.call_count, 2)

    def test_an_imap_cache_entry_is_never_served_for_graph(self):
        cache.set(f"{INBOX_LIST_CACHE_KEY}:INBOX:30", [{"uid": "imap-1"}])

        with patch(LIST_TARGET, autospec=True, return_value=[]):
            self.assertEqual(list_inbox_messages(limit=30), [])

    @patch(FETCH_TARGET, autospec=True, return_value=RAW_MIME)
    def test_fetch_reads_mime_through_graph_and_caches_it(self, fetch_mime):
        detail = fetch_inbox_message(MESSAGE_ID)
        again = fetch_inbox_message(MESSAGE_ID)

        self.assertEqual(detail, again)
        self.assertEqual(fetch_mime.call_count, 1)
        self.assertEqual(fetch_mime.call_args.args[1], MESSAGE_ID)
        self.assertEqual(detail["subject"], "Re: Event question")
        self.assertEqual(cache.get(f"{INBOX_MSG_CACHE_PREFIX}graph:INBOX:{MESSAGE_ID}"), detail)
        self.assertIsNone(cache.get(f"{INBOX_MSG_CACHE_PREFIX}INBOX:{MESSAGE_ID}"))

    def test_fetch_never_marks_the_message_read(self):
        with patch(LIST_TARGET, autospec=True, return_value=[{**GRAPH_MESSAGE, "isRead": False}]):
            list_inbox_messages(limit=30)
        with patch(FETCH_TARGET, autospec=True, return_value=RAW_MIME):
            fetch_inbox_message(MESSAGE_ID)

        self.assertFalse(cache.get(f"{INBOX_LIST_CACHE_KEY}:graph:INBOX:30")[0]["is_seen"])

    def test_reads_use_get_only(self):
        """End to end through the transport: one token POST to the identity platform, then only GETs to Graph."""
        get = MagicMock(return_value=HttpResponse(200, {}, RAW_MIME))
        token = HttpResponse(200, {}, b'{"access_token": "not-a-real-token", "expires_in": 3599}')
        post = MagicMock(return_value=token)
        with (
            patch("apps.core.services.email.graph.transport.get", get),
            patch("apps.core.services.email.graph.transport.post", post),
        ):
            auth.clear_access_token_cache()
            self.addCleanup(auth.clear_access_token_cache)
            fetch_inbox_message(MESSAGE_ID, folder="SENT")

        self.assertEqual([call.args[0] for call in post.call_args_list], ["login.microsoftonline.com"])
        self.assertEqual(get.call_args.args[1], f"/v1.0/users/{MAILBOX}/messages/{MESSAGE_ID}/$value")

    def test_graph_errors_surface_as_inbox_errors_and_are_not_cached(self):
        with patch(FETCH_TARGET, autospec=True, return_value=b"x") as fetch_mime:
            fetch_mime.side_effect = GraphReadError("Microsoft Graph is busy; try again in a minute.")
            with self.assertRaisesMessage(InboxError, "busy"):
                fetch_inbox_message(MESSAGE_ID)

        self.assertIsNone(cache.get(f"{INBOX_MSG_CACHE_PREFIX}graph:INBOX:{MESSAGE_ID}"))


class ImapFallbackTests(GraphInboxFixtureMixin, TestCase):
    def use_imap(self, messages):
        @contextmanager
        def fake_inbox(mailbox=None, folder="INBOX"):
            client = MagicMock()
            client.fetch.return_value = iter(messages)
            yield client

        self.open_inbox.side_effect = fake_inbox

    def test_send_only_scope_reads_through_imap(self):
        graph_config(permission=Permission.SEND)
        self.use_imap([])

        with patch(LIST_TARGET) as graph_list:
            self.assertEqual(list_inbox_messages(limit=30), [])

        graph_list.assert_not_called()
        self.open_inbox.assert_called_once()
        self.assertEqual(cache.get(f"{INBOX_LIST_CACHE_KEY}:INBOX:30"), [])

    def test_no_graph_config_reads_through_imap(self):
        self.use_imap([])

        with patch(FETCH_TARGET) as graph_fetch, self.assertRaisesMessage(InboxError, "Message not found."):
            fetch_inbox_message("42")

        graph_fetch.assert_not_called()

    def test_missing_tables_are_reported_as_an_inbox_error(self):
        for error in (OperationalError("no such table"), ProgrammingError("relation does not exist")):
            with self.subTest(type(error).__name__):
                target = "apps.mail.services.inbox.graph_backend.active_reader"
                with patch(target, side_effect=error), self.assertRaisesMessage(InboxError, "migrations"):
                    list_inbox_messages()
                with patch(target, side_effect=error), self.assertRaisesMessage(InboxError, "migrations"):
                    fetch_inbox_message("1")


class InboxAccountTests(GraphInboxFixtureMixin, TestCase):
    def test_graph_account_when_read_is_granted(self):
        graph_config()

        self.assertEqual(
            _inbox_account(),
            {"account": MAILBOX, "source_label": "Source", "source": "Microsoft Graph"},
        )

    def test_gmail_account_otherwise(self):
        graph_config(permission=Permission.SEND)
        GmailAccessAccount.objects.all().delete()
        GmailAccessAccount.objects.create(is_active=True, imap_host="imap.example.com", gmail_username="i2g@gmail.com")

        self.assertEqual(
            _inbox_account(), {"account": "i2g@gmail.com", "source_label": "IMAP host", "source": "imap.example.com"}
        )

    def test_a_reader_failure_falls_back_to_gmail_and_is_logged(self):
        with (
            patch("apps.mail.services.inbox.graph_backend.active_reader", side_effect=RuntimeError("boom")),
            self.assertLogs("apps.mail.admin.inbox", "ERROR"),
        ):
            account = _inbox_account()

        self.assertEqual(account["source_label"], "IMAP host")
