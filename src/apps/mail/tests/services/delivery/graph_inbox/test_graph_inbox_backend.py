"""``inbox.graph_backend``: choosing the Graph reader and mapping Graph data onto the IMAP dictionaries."""

from datetime import datetime

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.core.models import EmailServiceConfig, MicrosoftGraphProviderConfig
from apps.core.services.email.graph.mailbox import GraphMailboxReader
from apps.core.tests.graph_helpers import create_graph_config
from apps.mail.services.inbox.reading import graph_backend
from apps.mail.services.inbox.reading.connection import InboxError
from apps.mail.services.inbox.reading.formatting import format_date
from apps.mail.services.inbox.reading.messages import message_summary
from apps.mail.tests.services.delivery.graph_inbox.helpers import (
    CLIENT_ID,
    GRAPH_MESSAGE,
    MAILBOX,
    MESSAGE_ID,
    SUMMARY_KEYS,
    TENANT_ID,
    Permission,
    graph_config,
    imap_message,
)


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
