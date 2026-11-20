"""``inbox.graph_backend``: choosing the Graph reader and mapping Graph data onto the IMAP dictionaries."""

from datetime import datetime
from types import SimpleNamespace

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.core.models import EmailServiceConfig, MicrosoftGraphMailboxScope, MicrosoftGraphProviderConfig
from apps.core.services.email.graph.mailbox import GraphMailboxReader
from apps.core.tests.graph_helpers import create_graph_config
from apps.mail.services.inbox import graph_backend
from apps.mail.services.inbox.connection import InboxError
from apps.mail.services.inbox.formatting import format_date
from apps.mail.services.inbox.messages import message_summary

Permission = MicrosoftGraphMailboxScope.Permission
TENANT_ID = "11111111-2222-3333-4444-555555555555"
CLIENT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
MAILBOX = "i2g@contoso.com"
MESSAGE_ID = "AAMkAGI2THVSAAA="
SUMMARY_KEYS = {
    "uid", "subject", "from_name", "from_email", "to", "date", "timestamp", "snippet", "is_seen", "from_own_mailbox",
}  # fmt: skip
DETAIL_KEYS = {
    "uid", "subject", "from_name", "from_email", "to", "date", "timestamp", "html", "text",
    "message_id", "references", "reply_to", "return_path", "authentication_results", "from_own_mailbox",
}  # fmt: skip
# What the inbox services add to every summary / detail: the account each message was read from.
ACCOUNT_KEYS = {"account", "account_address"}
GRAPH_MESSAGE = {
    "id": MESSAGE_ID,
    "subject": "  Event question  ",
    "from": {"emailAddress": {"name": "Ada Lovelace", "address": "ada@example.com"}},
    "toRecipients": [
        {"emailAddress": {"name": "I2G", "address": MAILBOX}},
        {"emailAddress": {"address": "cc@example.com"}},
        "not a recipient",
    ],
    "receivedDateTime": "2026-10-20T15:30:00Z",
    "bodyPreview": "Hello\n\n  there   friend",
    "isRead": True,
}
RAW_MIME = b"""From: "Ada Lovelace" <ada@example.com>
To: I2G <i2g@contoso.com>, cc@example.com
Subject: Re: Event question
Date: Tue, 20 Oct 2026 15:30:00 +0000
Message-ID: <reply-1@example.com>
References: <root@example.com> <orig@example.com>
Reply-To: Replies <Replies@Example.com>
Return-Path: <Bounce@Example.com>
Authentication-Results: mx.contoso.com; spf=pass
Authentication-Results: mx.contoso.com; dkim=pass
MIME-Version: 1.0
Content-Type: multipart/alternative; boundary="b1"

--b1
Content-Type: text/plain; charset="utf-8"

Plain body
--b1
Content-Type: text/html; charset="utf-8"

<p>HTML body</p>
--b1--
"""


def imap_message(**overrides):
    values = {
        "uid": "7",
        "subject": "s",
        "from_values": None,
        "from_": "x@example.com",
        "to_values": [],
        "date": None,
        "html": "",
        "text": "",
        "flags": (),
        "headers": {},
    }
    return SimpleNamespace(**{**values, **overrides})


def graph_config(permission=Permission.SEND_AND_READ, **overrides):
    values = {
        "name": "Graph",
        "is_active": True,
        "tenant_id": TENANT_ID,
        "client_id": CLIENT_ID,
    }
    return create_graph_config(scope=(MAILBOX,), permission=permission, **{**values, **overrides})


class ActiveReaderTests(TestCase):
    def setUp(self):
        cache.clear()
        EmailServiceConfig.objects.all().delete()
        MicrosoftGraphProviderConfig.objects.all().delete()
        EmailServiceConfig.objects.create(name="Prod", is_active=True, provider="graph", from_email=MAILBOX)

    def test_returns_a_reader_for_the_sender_when_read_is_granted(self):
        graph_config()

        reader = graph_backend.active_reader()

        self.assertIsInstance(reader, GraphMailboxReader)
        self.assertEqual(reader.mailbox, MAILBOX)

    def test_uses_the_configured_mailbox_over_the_from_address(self):
        create_graph_config(
            scope=("shared@contoso.com",),
            name="Graph",
            is_active=True,
            tenant_id=TENANT_ID,
            client_id=CLIENT_ID,
            mailbox="Shared@Contoso.com",
        )

        self.assertEqual(graph_backend.active_reader().mailbox, "shared@contoso.com")

    def test_none_without_read_permission(self):
        graph_config(permission=Permission.SEND)

        self.assertIsNone(graph_backend.active_reader())

    def test_none_when_graph_is_not_configured(self):
        self.assertIsNone(graph_backend.active_reader())
        graph_config(is_active=False)
        self.assertIsNone(graph_backend.active_reader())


class ReaderForTests(TestCase):
    def setUp(self):
        cache.clear()
        EmailServiceConfig.objects.all().delete()
        MicrosoftGraphProviderConfig.objects.all().delete()
        EmailServiceConfig.objects.create(name="Prod", is_active=True, provider="graph", from_email=MAILBOX)

    def test_returns_a_reader_for_a_mailbox_with_read(self):
        graph_config()

        reader = graph_backend.reader_for(MAILBOX)

        self.assertIsInstance(reader, GraphMailboxReader)
        self.assertEqual(reader.mailbox, MAILBOX)

    def test_refuses_a_send_only_or_unscoped_mailbox(self):
        graph_config(permission=Permission.SEND)

        for mailbox in (MAILBOX, "other@contoso.com"):
            with self.subTest(mailbox), self.assertRaisesMessage(InboxError, "not available"):
                graph_backend.reader_for(mailbox)

    def test_refuses_when_graph_is_not_configured(self):
        with self.assertRaisesMessage(InboxError, "not available"):
            graph_backend.reader_for(MAILBOX)


class SummaryTests(TestCase):
    def test_has_the_same_keys_as_the_imap_summary(self):
        summary = graph_backend._summary(GRAPH_MESSAGE)

        self.assertEqual(set(summary), SUMMARY_KEYS)
        self.assertEqual(set(summary), set(message_summary(imap_message())))

    def test_maps_graph_fields(self):
        summary = graph_backend._summary(GRAPH_MESSAGE)

        received = timezone.localtime(datetime.fromisoformat("2026-10-20T15:30:00+00:00"))
        self.assertEqual(
            summary,
            {
                "uid": MESSAGE_ID,
                "subject": "Event question",
                "from_name": "Ada Lovelace",
                "from_email": "ada@example.com",
                "to": [{"name": "I2G", "email": MAILBOX}, {"name": "", "email": "cc@example.com"}],
                "date": format_date(received),
                "timestamp": received.timestamp(),
                "snippet": "Hello there friend",
                "is_seen": True,
                "from_own_mailbox": False,
            },
        )

    def test_missing_fields_get_safe_defaults(self):
        summary = graph_backend._summary({"id": MESSAGE_ID, "from": None, "toRecipients": None})

        self.assertEqual(summary["subject"], "(No subject)")
        self.assertEqual((summary["from_name"], summary["from_email"], summary["to"]), ("", "", []))
        self.assertEqual((summary["snippet"], summary["is_seen"]), ("", False))
        self.assertEqual(summary["date"], format_date(None))
        self.assertEqual(summary["timestamp"], 0.0)

    def test_long_previews_are_shortened(self):
        summary = graph_backend._summary({"id": MESSAGE_ID, "bodyPreview": "word " * 100})

        self.assertTrue(summary["snippet"].endswith("..."))
        self.assertLessEqual(len(summary["snippet"]), 200)

    def test_naive_timestamps_are_kept(self):
        summary = graph_backend._summary({"id": MESSAGE_ID, "receivedDateTime": "2026-10-20T15:30:00"})

        self.assertEqual(summary["date"], format_date(datetime(2026, 10, 20, 15, 30)))
