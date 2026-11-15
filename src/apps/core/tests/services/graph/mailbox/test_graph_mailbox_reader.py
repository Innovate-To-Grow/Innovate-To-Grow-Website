"""``GraphMailboxReader``: scope enforcement, the request shapes for listing and MIME, and error handling.

``transport.post`` (token requests) is replaced by ``FakeGraph`` and ``transport.get`` by ``FakeGet`` below, so no
test opens a socket.
"""

import json
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase

from apps.core.models import MicrosoftGraphMailboxScope
from apps.core.services.email.graph.access import GraphScopeError
from apps.core.services.email.graph.mailbox import (
    LIST_FIELDS,
    GraphMailboxReader,
    GraphReadError,
)
from apps.core.services.email.graph.provider import GRAPH_HOST
from apps.core.services.email.graph.transport import HttpResponse
from apps.core.tests.graph_helpers import create_graph_config, grant
from apps.core.tests.services.graph.provider.test_email_graph import (
    ACCESS_TOKEN,
    CLIENT_ID,
    TENANT_ID,
    GraphFixtureMixin,
)

Permission = MicrosoftGraphMailboxScope.Permission
GET_TARGET = "apps.core.services.email.graph.transport.get"
MAILBOX = "i2g@contoso.com"
MESSAGE_ID = "AAMkAGI2THVSAAA="


class FakeGet:
    """Stands in for ``transport.get``; an outcome is an ``HttpResponse``, an exception, or a list consumed in order."""

    def __init__(self, outcome=None):
        self.calls = []
        self.outcome = outcome if outcome is not None else HttpResponse(200, {}, b'{"value": []}')

    def __call__(self, host, path, headers, *, timeout, max_bytes):
        self.calls.append({"host": host, "path": path, "headers": headers, "timeout": timeout, "max_bytes": max_bytes})
        outcome = self.outcome
        if isinstance(outcome, list):
            outcome = outcome.pop(0) if len(outcome) > 1 else outcome[0]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def listing(*messages):
    return HttpResponse(200, {}, json.dumps({"value": list(messages)}).encode())


class GraphReaderFixtureMixin(GraphFixtureMixin):
    def setUp(self):
        super().setUp()
        self.get = FakeGet()
        patcher = patch(GET_TARGET, new=self.get)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.config = create_graph_config(
            scope=(MAILBOX,),
            name="Graph",
            is_active=True,
            tenant_id=TENANT_ID,
            client_id=CLIENT_ID,
        )

    def reader(self, mailbox=MAILBOX, **kwargs):
        return GraphMailboxReader(self.config, mailbox, **kwargs)

    def tearDown(self):
        # Mail.Read only: the reader never posts to Graph (the identity platform is the only POST target).
        self.assertEqual(self.fake.send_requests, [])
        super().tearDown()


class GraphReaderScopeTests(GraphReaderFixtureMixin, TestCase):
    def test_refuses_a_mailbox_outside_the_scope_before_any_request(self):
        with self.assertRaises(GraphScopeError):
            self.reader("someone@contoso.com")
        self.assertEqual((self.fake.requests, self.get.calls), ([], []))

    def test_refuses_a_send_only_mailbox(self):
        grant(self.config, "send-only@contoso.com", permission=Permission.SEND)

        with self.assertRaisesMessage(GraphScopeError, "may not read"):
            self.reader("send-only@contoso.com")
        self.assertEqual(self.get.calls, [])

    def test_accepts_a_read_only_mailbox(self):
        grant(self.config, "read-only@contoso.com", permission=Permission.READ)

        reader = self.reader("read-only@contoso.com", timeout=5)

        self.assertEqual((reader.mailbox, reader.timeout), ("read-only@contoso.com", 5))
        self.assertEqual(reader.credential.key_version_id, self.config.current_certificate.store_version_id)


class GraphReaderListTests(GraphReaderFixtureMixin, TestCase):
    def test_lists_the_inbox_with_a_bearer_token(self):
        message = {"id": MESSAGE_ID, "subject": "Hello"}
        self.get.outcome = listing(message)

        self.assertEqual(self.reader().list_messages("INBOX", 30), [message])

        (call,) = self.get.calls
        self.assertEqual(call["host"], GRAPH_HOST)
        self.assertEqual(
            call["path"],
            f"/v1.0/users/{MAILBOX}/mailFolders/inbox/messages"
            f"?$top=30&$select={LIST_FIELDS}&$orderby=receivedDateTime%20desc",
        )
        self.assertEqual(call["headers"], {"Authorization": f"Bearer {ACCESS_TOKEN}", "Accept": "application/json"})
        self.assertEqual(
            (call["max_bytes"], call["timeout"]),
            (settings.GRAPH_INBOX_LIST_MAX_BYTES, settings.GRAPH_REQUEST_TIMEOUT_SECONDS),
        )

    def test_folder_names_map_to_well_known_folders(self):
        reader = self.reader()
        for folder, expected in (
            ("SENT", "sentitems"),
            ("sent", "sentitems"),
            ("Archive", "inbox"),
            ("inbox", "inbox"),
        ):
            with self.subTest(folder):
                self.get.calls.clear()
                reader.list_messages(folder, 10)
                self.assertIn(f"/mailFolders/{expected}/messages?", self.get.calls[0]["path"])

    def test_limit_is_clamped_between_1_and_100(self):
        reader = self.reader()
        for limit, top in ((0, 1), (-5, 1), (100, 100), (500, 100), ("25", 25)):
            with self.subTest(limit):
                self.get.calls.clear()
                reader.list_messages("INBOX", limit)
                self.assertIn(f"?$top={top}&", self.get.calls[0]["path"])
        with self.settings(GRAPH_INBOX_MAX_LIST_LIMIT=10):
            self.get.calls.clear()
            reader.list_messages("INBOX", 50)
            self.assertIn("?$top=10&", self.get.calls[0]["path"])

    def test_messages_with_invalid_ids_are_dropped(self):
        good = {"id": MESSAGE_ID}
        self.get.outcome = listing(good, {"id": "../evil"}, {"id": ""}, {"subject": "no id"}, "not a dict")

        self.assertEqual(self.reader().list_messages("INBOX", 30), [good])

    def test_the_mailbox_is_quoted_in_the_url(self):
        grant(self.config, "o'brien+x@contoso.com")

        self.reader("o'brien+x@contoso.com").list_messages("INBOX", 1)

        self.assertTrue(self.get.calls[0]["path"].startswith("/v1.0/users/o%27brien%2Bx@contoso.com/"))

    def test_unreadable_or_truncated_lists_raise(self):
        for label, response in {
            "not json": HttpResponse(200, {}, b"<html>"),
            "no value": HttpResponse(200, {}, b"{}"),
            "value not a list": HttpResponse(200, {}, b'{"value": {}}'),
            "json list": HttpResponse(200, {}, b"[]"),
            "truncated": HttpResponse(200, {}, b'{"value": []}', truncated=True),
        }.items():
            with self.subTest(label):
                self.get.outcome = response
                with self.assertRaisesMessage(GraphReadError, "unreadable message list"):
                    self.reader().list_messages("INBOX", 5)
