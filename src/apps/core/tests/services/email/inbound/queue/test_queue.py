"""The inbound queue: recording listed messages once, the consumer's claim and settle steps, retention, and the
registry through which an app that lists the Inbox on its own schedule describes itself to the Email Monitoring card.
No consumer app is involved, except where the helpdesk's own registration is checked."""

from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.db import DataError
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.core.models import InboundMessage
from apps.core.services.email.inbound import (
    LINK_PLACEHOLDER,
    InboxReader,
    format_interval,
    inbox_readers,
    pending_count,
    record,
    register_inbox_reader,
    registered_inbox_readers,
    registry,
)

SITE = "i2g@ucmerced.edu"
Status = InboundMessage.Status
TOKEN = "fake-test-token-0000000000"  # a synthetic value: only its position matters
READER = InboxReader("Test reader", "paused", 120, "/admin/test/")


def listed(graph_id="AAMk-1", **values):
    message = {
        "id": graph_id,
        "subject": f"Re: your link https://i2g.ucmerced.edu/login-link#token={TOKEN}",
        "from": {"emailAddress": {"address": "Pat@Example.org", "name": "Pat Doe"}},
        "internetMessageId": "<m1@example.org>",
        "conversationId": "AAQkADAwATM0MDAAMS1iZjQ2",
    }
    return {**message, **values}


def row(**values):
    defaults = {
        "mailbox": SITE,
        "graph_id": f"AAMk-{InboundMessage.objects.count() + 1}",
        "received_at": timezone.now(),
    }
    return InboundMessage.objects.create(**{**defaults, **values})


def describe_test_reader():
    return READER


def describe_nothing_useful():
    return {"label": "not an InboxReader"}


class InboxReaderRegistryTests(SimpleTestCase):
    def setUp(self):
        self.saved = dict(registry._READERS)
        self.addCleanup(self.restore)

    def restore(self):
        registry._READERS.clear()
        registry._READERS.update(self.saved)

    def test_registering_again_needs_the_same_description(self):
        path = f"{__name__}.describe_test_reader"
        register_inbox_reader("test", describe=path)
        register_inbox_reader("test", describe=path)

        with self.assertRaises(ImproperlyConfigured):
            register_inbox_reader("test", describe=f"{__name__}.describe_nothing_useful")
        for name, describe in (("", path), ("nameless", "")):
            with self.subTest(name=name), self.assertRaises(ImproperlyConfigured):
                register_inbox_reader(name, describe=describe)
        self.assertEqual(registered_inbox_readers()["test"], path)

    def test_readers_describe_themselves_in_order_and_a_broken_one_never_breaks_the_page(self):
        registry._READERS.clear()
        register_inbox_reader("good", describe=f"{__name__}.describe_test_reader")
        register_inbox_reader("missing", describe="apps.nowhere.describe")
        register_inbox_reader("odd", describe=f"{__name__}.describe_nothing_useful")

        with self.assertLogs("apps.core.services.email.inbound.registry", level="ERROR") as logs:
            self.assertEqual(inbox_readers(), [READER])

        self.assertEqual(len(logs.records), 2)
        self.assertIn("missing", logs.records[0].getMessage())
        self.assertIn("odd described itself as dict", logs.records[1].getMessage())

    def test_the_helpdesk_registers_its_intake(self):
        self.assertEqual(registered_inbox_readers()["helpdesk"], "apps.helpdesk.services.intake.status.describe")

    def test_a_cadence_reads_as_people_say_it(self):
        cases = {600: "10 min", 120: "2 min", 60: "1 min", 90: "90 s", 30: "30 s", 3600: "1 h", 5400: "1 h 30 min"}
        for seconds, text in cases.items():
            with self.subTest(seconds=seconds):
                self.assertEqual(format_interval(seconds), text)
        self.assertEqual(READER.every, "2 min")


class RecordTests(TestCase):
    def setUp(self):
        cache.clear()
        self.received = timezone.now() - timedelta(minutes=3)

    def test_a_listed_message_is_recorded_once_with_cleaned_metadata(self):
        self.assertTrue(record(SITE, listed(), self.received, candidate=False))
        self.assertFalse(record(SITE, listed(), self.received, candidate=False))

        stored = InboundMessage.objects.get()
        self.assertEqual(
            (stored.mailbox, stored.graph_id, stored.status, stored.kind, stored.folder),
            (SITE, "AAMk-1", Status.PENDING, InboundMessage.Kind.MESSAGE, "inbox"),
        )
        self.assertEqual((stored.from_address, stored.from_name), ("pat@example.org", "Pat Doe"))
        self.assertEqual(stored.subject, f"Re: your link {LINK_PLACEHOLDER}")
        self.assertEqual(
            (stored.internet_message_id, stored.conversation_id), ("<m1@example.org>", "AAQkADAwATM0MDAAMS1iZjQ2")
        )
        self.assertEqual(stored.received_at, self.received)
        self.assertEqual(pending_count(), 1)

    def test_a_bounce_candidate_is_recorded_as_one(self):
        record(SITE, listed(), self.received, candidate=True)

        self.assertEqual(InboundMessage.objects.get().kind, InboundMessage.Kind.BOUNCE_CANDIDATE)

    def test_the_same_graph_id_in_another_mailbox_is_another_message(self):
        record(SITE, listed(), self.received, candidate=False)

        self.assertTrue(record("other@ucmerced.edu", listed(), self.received, candidate=False))

    def test_nothing_is_recorded_without_an_id(self):
        self.assertFalse(record(SITE, listed(graph_id=""), self.received, candidate=False))
        self.assertFalse(InboundMessage.objects.exists())

    def test_hostile_values_are_bounded(self):
        message = listed(subject="word " * 400, conversationId="C" * 900, internetMessageId="<" + "x" * 300 + ">")
        message["from"] = {"emailAddress": {"address": "not an address", "name": "N\x00" * 400}}

        self.assertTrue(record(SITE, message, self.received, candidate=False))

        stored = InboundMessage.objects.get()
        self.assertEqual((len(stored.subject), len(stored.conversation_id)), (255, 255))
        self.assertEqual((stored.internet_message_id, stored.from_address), ("", ""))
        self.assertNotIn("\x00", stored.from_name)

    def test_a_nul_in_the_message_id_does_not_keep_the_message_out(self):
        # PostgreSQL text cannot hold NUL: kept, it would make the insert fail and the scan move past the message.
        self.assertTrue(record(SITE, listed(internetMessageId="<m1\x00@example.org>"), self.received, candidate=False))

        self.assertEqual(InboundMessage.objects.get().internet_message_id, "<m1@example.org>")

    def test_a_row_recorded_by_another_process_meanwhile_is_not_an_error(self):
        record(SITE, listed(), self.received, candidate=False)
        with patch("apps.core.services.email.inbound.queue.InboundMessage.objects.filter") as lookup:
            lookup.return_value.exists.return_value = False
            self.assertFalse(record(SITE, listed(), self.received, candidate=False))

        self.assertEqual(InboundMessage.objects.count(), 1)
        self.assertEqual(str(InboundMessage.objects.get()), f"pat@example.org: Re: your link {LINK_PLACEHOLDER}")
        self.assertEqual(str(InboundMessage(mailbox=SITE)), "unknown sender: (no subject)")

    def test_a_value_the_database_refuses_is_skipped_and_the_scan_goes_on(self):
        with (
            patch.object(InboundMessage.objects, "create", side_effect=DataError("value too long")),
            self.assertLogs("apps.core.services.email.inbound.queue", level="WARNING"),
        ):
            self.assertFalse(record(SITE, listed(), self.received, candidate=False))
