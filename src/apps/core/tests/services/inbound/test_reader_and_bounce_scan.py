"""The bounce scan reads the Inbox for reports only and records nothing in the inbound queue (the helpdesk's intake
lists the Inbox with its own scan and checkpoint); the reader asks for the conversation id, sends the immutable-id
preference only when switched on, and the Graph allow-list is unchanged: reading only. Graph is never contacted."""

from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.core.models import EmailBounce, EmailMonitorState, InboundMessage
from apps.core.services.email.bounces import scanner
from apps.core.services.email.graph import transport
from apps.core.services.email.graph.mailbox import IMMUTABLE_ID_PREFERENCE, SCAN_FIELDS
from apps.core.tests.services.email_monitoring.helpers import SENDER, make_email, monitoring_settings
from apps.core.tests.services.email_monitoring.ndr_samples import ORIGINAL_ID, exchange_ndr, personal_email
from apps.core.tests.services.email_monitoring.test_bounce_scanner import FakeReader, listed
from apps.core.tests.services.test_graph_mailbox_reader import MAILBOX, GraphReaderFixtureMixin, listing

READER = "apps.core.services.email.bounces.scanner.active_reader"


class BounceScanRecordsNothingTests(TestCase):
    def setUp(self):
        cache.clear()
        self.now = timezone.now().replace(microsecond=0)
        make_email(internet_message_id=ORIGINAL_ID, recipient="nobody@example.com")
        self.messages = [
            listed(
                "ndr-1",
                subject="Undeliverable: Hello",
                sender="postmaster@x.example",
                received=self.now - timedelta(minutes=30),
            ),
            listed(
                "human-1", subject="Question", sender="person@example.com", received=self.now - timedelta(minutes=20)
            ),
        ]
        self.bodies = {"ndr-1": exchange_ndr(), "human-1": personal_email()}

    def test_the_bounce_scan_handles_reports_and_leaves_the_inbound_queue_alone(self):
        reader = FakeReader(self.messages, self.bodies)

        with patch(READER, return_value=(reader, SENDER, "")), monitoring_settings():
            outcome = scanner.scan_mailbox(now=self.now)

        self.assertEqual(outcome.status, "ok")
        self.assertNotIn("recorded", outcome.stats)
        self.assertEqual((outcome.stats["listed"], reader.opened), (2, ["ndr-1"]))
        self.assertEqual(EmailBounce.objects.count(), 1)
        self.assertEqual(EmailMonitorState.objects.get(mailbox=SENDER).checkpoint_at, self.now)
        self.assertFalse(InboundMessage.objects.exists())


class ReaderRequestTests(GraphReaderFixtureMixin, TestCase):
    def test_the_incremental_listing_asks_for_the_conversation_id(self):
        self.get.outcome = listing()

        self.reader().list_received_since("INBOX", timezone.now(), 50)

        (call,) = self.get.calls
        self.assertIn("conversationId", SCAN_FIELDS)
        self.assertIn(f"$select={SCAN_FIELDS}&", call["path"])
        self.assertTrue(transport.is_allowed("GET", "graph.microsoft.com", call["path"]))

    def test_the_immutable_id_preference_is_sent_only_when_switched_on(self):
        self.get.outcome = listing()
        self.reader().list_received_since("INBOX", timezone.now(), 50)
        self.assertNotIn("Prefer", self.get.calls[-1]["headers"])

        with monitoring_settings(graph_immutable_ids=True):
            self.reader().list_received_since("INBOX", timezone.now(), 50)

        self.assertEqual(self.get.calls[-1]["headers"]["Prefer"], IMMUTABLE_ID_PREFERENCE)
        self.assertEqual(IMMUTABLE_ID_PREFERENCE, 'IdType="ImmutableId"')


class AllowListTests(TestCase):
    def test_the_graph_allow_list_still_only_reads_and_sends(self):
        """No new Microsoft Graph request (no PATCH, move, forward or mark-read) came with the inbound queue."""
        self.assertEqual(
            [(method, host) for method, host, _pattern in transport.ALLOWED_REQUESTS],
            [
                ("POST", transport.AUTHORITY_HOST),
                ("POST", transport.GRAPH_HOST),
                ("GET", transport.GRAPH_HOST),
                ("GET", transport.GRAPH_HOST),
                ("GET", transport.GRAPH_HOST),
            ],
        )
        user = f"/v1.0/users/{MAILBOX}"
        for method, path in (
            ("PATCH", f"{user}/messages/AAMk"),
            ("POST", f"{user}/messages/AAMk/move"),
            ("POST", f"{user}/messages/AAMk/forward"),
            ("POST", f"{user}/messages/AAMk/reply"),
            ("GET", f"{user}/mailFolders/junkemail/messages"),
        ):
            with self.subTest(method=method, path=path):
                self.assertFalse(transport.is_allowed(method, transport.GRAPH_HOST, path))
