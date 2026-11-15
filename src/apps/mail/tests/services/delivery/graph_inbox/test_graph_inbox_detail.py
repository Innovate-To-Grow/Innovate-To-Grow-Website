from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.core.models import EmailServiceConfig
from apps.core.services.email.graph.mailbox import GraphMessageNotFound, GraphReadError
from apps.mail.services.inbox import graph_backend
from apps.mail.services.inbox.connection import InboxError
from apps.mail.services.inbox.formatting import format_date
from apps.mail.services.inbox.messages import detailed_message
from apps.mail.tests.services.delivery.graph_inbox.test_graph_inbox_backend import (
    DETAIL_KEYS,
    GRAPH_MESSAGE,
    MAILBOX,
    MESSAGE_ID,
    RAW_MIME,
    imap_message,
)


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
