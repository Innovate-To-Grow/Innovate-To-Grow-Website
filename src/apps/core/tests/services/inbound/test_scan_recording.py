"""The bounce scan records every listed message in the inbound queue (once), still handles bounce reports as before,
and moves its checkpoint past what it recorded. The reader asks for the conversation id, sends the immutable-id
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


class ScanRecordingTests(TestCase):
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
            listed("human-2", subject="Thanks", sender="other@example.com", received=self.now - timedelta(minutes=10)),
        ]
        self.messages[1]["conversationId"] = "AAQkConversation1"
        self.bodies = {"ndr-1": exchange_ndr(), "human-1": personal_email(), "human-2": personal_email()}

    def scan(self, reader, **settings_changes):
        with patch(READER, return_value=(reader, SENDER, "")), monitoring_settings(**settings_changes):
            return scanner.scan_mailbox(now=self.now)

    def test_every_listed_message_is_recorded_once_and_bounces_still_processed(self):
        reader = FakeReader(self.messages, self.bodies)

        outcome = self.scan(reader)

        self.assertEqual(outcome.status, "ok")
        self.assertEqual(outcome.stats["recorded"], 3)
        rows = {row.graph_id: row for row in InboundMessage.objects.all()}
        self.assertEqual(set(rows), {"ndr-1", "human-1", "human-2"})
        self.assertEqual(rows["ndr-1"].kind, InboundMessage.Kind.BOUNCE_CANDIDATE)
        self.assertEqual(rows["human-1"].kind, InboundMessage.Kind.MESSAGE)
        self.assertEqual(rows["human-1"].conversation_id, "AAQkConversation1")
        self.assertEqual({row.status for row in rows.values()}, {InboundMessage.Status.PENDING})
        # The bounce path is unchanged: only the candidate was opened, and its bounce stored.
        self.assertEqual(reader.opened, ["ndr-1"])
        self.assertEqual(EmailBounce.objects.count(), 1)
        self.assertEqual(EmailMonitorState.objects.get(mailbox=SENDER).checkpoint_at, self.now)

    def test_the_overlap_lists_messages_again_but_records_none_twice(self):
        reader = FakeReader(self.messages, self.bodies)
        self.scan(reader)
        EmailMonitorState.objects.filter(mailbox=SENDER).update(checkpoint_at=self.now - timedelta(minutes=5))

        outcome = self.scan(reader)

        self.assertEqual(outcome.stats["recorded"], 0)
        self.assertGreater(outcome.stats["listed"], 0)
        self.assertEqual(InboundMessage.objects.count(), 3)

    def test_a_scan_that_stops_at_its_budget_has_recorded_what_it_passed(self):
        reader = FakeReader(self.messages, self.bodies)

        outcome = self.scan(reader, bounce_scan_max_messages=0)

        self.assertEqual(outcome.status, "partial")
        # The candidate came first and the budget stopped the page there: it is recorded, nothing after it is.
        self.assertEqual(list(InboundMessage.objects.values_list("graph_id", flat=True)), ["ndr-1"])
        self.assertIsNone(EmailMonitorState.objects.get(mailbox=SENDER).checkpoint_at)


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
