"""``inbox.graph_backend``: choosing the Graph reader and mapping Graph data onto the IMAP dictionaries."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.core.models import EmailServiceConfig, MicrosoftGraphMailboxScope, MicrosoftGraphProviderConfig
from apps.core.services.email.graph.mailbox import GraphMailboxReader, GraphMessageNotFound, GraphReadError
from apps.core.tests.graph_helpers import create_graph_config
from apps.mail.services.inbox import graph_backend
from apps.mail.services.inbox.connection import InboxError
from apps.mail.services.inbox.formatting import format_date
from apps.mail.services.inbox.messages import detailed_message, message_summary

Permission = MicrosoftGraphMailboxScope.Permission
TENANT_ID = "11111111-2222-3333-4444-555555555555"
CLIENT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
MAILBOX = "i2g@contoso.com"
MESSAGE_ID = "AAMkAGI2THVSAAA="
SUMMARY_KEYS = {"uid", "subject", "from_name", "from_email", "to", "date", "snippet", "is_seen", "from_own_mailbox"}
DETAIL_KEYS = {
    "uid", "subject", "from_name", "from_email", "to", "date", "html", "text",
    "message_id", "references", "reply_to", "return_path", "authentication_results", "from_own_mailbox",
}  # fmt: skip
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

    def test_long_previews_are_shortened(self):
        summary = graph_backend._summary({"id": MESSAGE_ID, "bodyPreview": "word " * 100})

        self.assertTrue(summary["snippet"].endswith("..."))
        self.assertLessEqual(len(summary["snippet"]), 200)

    def test_naive_timestamps_are_kept(self):
        summary = graph_backend._summary({"id": MESSAGE_ID, "receivedDateTime": "2026-10-20T15:30:00"})

        self.assertEqual(summary["date"], format_date(datetime(2026, 10, 20, 15, 30)))


class DetailTests(TestCase):
    def detail(self, raw=RAW_MIME):
        reader = SimpleNamespace(fetch_mime=lambda uid: raw, mailbox=MAILBOX)
        return graph_backend.fetch_message(reader, MESSAGE_ID)

    def test_has_the_same_keys_as_the_imap_detail(self):
        detail = self.detail()

        self.assertEqual(set(detail), DETAIL_KEYS)
        self.assertEqual(set(detail), set(detailed_message(imap_message())))

    def test_parses_headers_and_bodies(self):
        detail = self.detail()

        self.assertEqual(detail["uid"], MESSAGE_ID)
        self.assertEqual(detail["subject"], "Re: Event question")
        self.assertEqual((detail["from_name"], detail["from_email"]), ("Ada Lovelace", "ada@example.com"))
        self.assertEqual(detail["to"], [{"name": "I2G", "email": MAILBOX}, {"name": "", "email": "cc@example.com"}])
        self.assertEqual((detail["text"], detail["html"]), ("Plain body", "<p>HTML body</p>"))
        self.assertEqual(detail["message_id"], "<reply-1@example.com>")
        self.assertEqual(detail["references"], "<root@example.com> <orig@example.com>")
        self.assertEqual((detail["reply_to"], detail["return_path"]), ("replies@example.com", "bounce@example.com"))
        self.assertEqual(detail["authentication_results"], "mx.contoso.com; spf=pass mx.contoso.com; dkim=pass")
        sent = timezone.localtime(datetime.fromisoformat("2026-10-20T15:30:00+00:00"))
        self.assertEqual(detail["date"], format_date(sent))

    def test_html_only_messages_get_a_text_version(self):
        raw = b"Subject: x\r\nContent-Type: text/html; charset=utf-8\r\n\r\n<p>Only <b>HTML</b></p>"

        detail = self.detail(raw)

        self.assertEqual(detail["html"], "<p>Only <b>HTML</b></p>")
        self.assertIn("HTML", detail["text"])
        self.assertNotIn("<", detail["text"])

    def test_sparse_messages_get_safe_defaults(self):
        detail = self.detail(b"\r\nbody only")

        self.assertEqual(detail["subject"], "(No subject)")
        self.assertEqual((detail["from_email"], detail["to"], detail["date"]), ("", [], format_date(None)))
        self.assertEqual((detail["message_id"], detail["references"], detail["authentication_results"]), ("", "", ""))

    def test_malformed_headers_do_not_break_the_detail(self):
        raw = b"To: <<<\r\nDate: not a date\r\nSubject: s\r\n\r\nbody"

        detail = self.detail(raw)

        self.assertEqual(detail["subject"], "s")
        self.assertEqual(detail["date"], format_date(None))

    def test_undecodable_body_is_logged_and_left_blank(self):
        with patch("email.message.EmailMessage.get_body", side_effect=LookupError("bad charset")):
            with self.assertLogs("apps.mail.services.inbox.graph_backend", "WARNING"):
                detail = self.detail()

        self.assertEqual((detail["html"], detail["text"]), ("", ""))

    def test_mail_from_the_site_mailbox_or_its_from_address_is_flagged_as_own(self):
        # A Graph id is unique in the whole mailbox, so the views use this flag to treat such mail as Sent mail.
        EmailServiceConfig.objects.create(name="Mail", is_active=True, from_email="Noreply@Contoso.com")
        cases = {
            f"Innovate to Grow <{MAILBOX.upper()}>": True,
            "noreply@contoso.com": True,
            '"Ada Lovelace" <ada@example.com>': False,
        }
        for sender, own in cases.items():
            with self.subTest(sender=sender):
                detail = self.detail(f"From: {sender}\r\nSubject: s\r\n\r\nbody".encode())

                self.assertIs(detail["from_own_mailbox"], own)

    def test_mail_without_a_sender_is_not_own_even_without_a_from_address(self):
        EmailServiceConfig.objects.create(name="Mail", is_active=True, from_email="")

        self.assertIs(self.detail(b"Subject: s\r\n\r\nbody")["from_own_mailbox"], False)

    def test_header_helpers_tolerate_unparseable_values(self):
        message = SimpleNamespace(get=lambda header: object())

        self.assertEqual(graph_backend._addresses(message, "To"), [])
        self.assertIsNone(graph_backend._message_date(message))


class ErrorMappingTests(TestCase):
    def test_list_errors_become_inbox_errors(self):
        reader = SimpleNamespace(list_messages=lambda folder, limit: (_ for _ in ()).throw(GraphReadError("busy")))

        with self.assertRaisesMessage(InboxError, "busy"):
            graph_backend.list_messages(reader, folder="INBOX", limit=5)

    def test_fetch_errors_become_inbox_errors(self):
        for error, message in ((GraphMessageNotFound("x"), "Message not found."), (GraphReadError("denied"), "denied")):
            with self.subTest(type(error).__name__):
                reader = SimpleNamespace(fetch_mime=lambda uid, error=error: (_ for _ in ()).throw(error))
                with self.assertRaisesMessage(InboxError, message):
                    graph_backend.fetch_message(reader, MESSAGE_ID)

    def test_list_maps_each_message(self):
        reader = SimpleNamespace(mailbox=MAILBOX, list_messages=lambda folder, limit: [GRAPH_MESSAGE, {"id": "B"}])

        results = graph_backend.list_messages(reader, folder="SENT", limit=2)

        self.assertEqual([item["uid"] for item in results], [MESSAGE_ID, "B"])

    def test_list_rows_from_the_site_mailbox_or_its_from_address_are_flagged_as_own(self):
        EmailServiceConfig.objects.create(name="Mail", is_active=True, from_email="Noreply@Contoso.com")
        senders = [MAILBOX.upper(), "noreply@contoso.com", "ada@example.com", ""]
        messages = [{"id": str(index), "from": {"emailAddress": {"address": a}}} for index, a in enumerate(senders)]
        reader = SimpleNamespace(mailbox=MAILBOX, list_messages=lambda folder, limit: messages)

        results = graph_backend.list_messages(reader, folder="INBOX", limit=4)

        self.assertEqual([item["from_own_mailbox"] for item in results], [True, True, False, False])
