"""Ticket numbers, staff actions on tickets (each in the audit trail), retention, and the event descriptions."""

from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.db import IntegrityError, connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.core.models import InboundMessage

from ..models import (
    HelpdeskSettings,
    IngestRecord,
    Ticket,
    TicketAttachment,
    TicketCategory,
    TicketEvent,
    TicketMessage,
)
from ..services import events, numbering, retention, tickets
from . import corpus
from .helpers import FakeReader, helpdesk_staff, make_admin, make_superuser, receive

Status = Ticket.Status
Kind = TicketEvent.Kind


def new_ticket(**values) -> Ticket:
    values.setdefault("subject", "Question")
    values.setdefault("requester_email", "pat@example.org")
    return numbering.create_ticket(**values)


class NumberingTests(TestCase):
    def test_numbers_start_at_1001_and_never_repeat(self):
        numbers = [new_ticket().number for _ in range(5)]

        self.assertEqual(len(set(numbers)), 5)
        self.assertEqual(numbers, sorted(numbers))
        self.assertGreaterEqual(numbers[0], numbering.FIRST_NUMBER)
        if connection.vendor != "postgresql":
            self.assertEqual(numbers[0], 1001)

    def test_postgresql_numbers_come_from_the_sequence_starting_at_1001(self):
        if connection.vendor != "postgresql":
            self.skipTest("The sequence exists on PostgreSQL only (SQLite takes the highest number plus one).")
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT start_value, min_value FROM pg_sequences WHERE sequencename = %s", [numbering.SEQUENCE]
            )
            self.assertEqual(cursor.fetchone(), (1001, 1001))

    def test_without_a_sequence_the_highest_number_plus_one_is_used(self):
        highest = new_ticket()
        with patch.object(numbering.connection, "vendor", "sqlite"):
            self.assertEqual(numbering.next_number(), highest.number + 1)

    def test_a_number_taken_meanwhile_is_skipped(self):
        taken = new_ticket()
        free = taken.number + 1
        with patch.object(numbering, "next_number", side_effect=[taken.number, free]):
            self.assertEqual(new_ticket().number, free)

    def test_creation_gives_up_after_its_attempts(self):
        taken = new_ticket()
        with patch.object(numbering, "next_number", return_value=taken.number), self.assertRaises(IntegrityError):
            new_ticket()

    def test_numbers_typed_by_staff_and_subject_tokens(self):
        for typed in ("1234", "#1234", "I2G-#1234", " [i2g-#1234] "):
            with self.subTest(typed):
                self.assertEqual(numbering.parse_number(typed), 1234)
        self.assertIsNone(numbering.parse_number("pat@example.org"))
        self.assertEqual(numbering.subject_numbers("Re: [I2G-#1002] and I2G-#1003 and [I2G-#1002]"), [1002, 1003])
        self.assertEqual(numbering.display(1005), "I2G-#1005")


class SequenceResetTests(TransactionTestCase):
    """Django resets column-owned sequences to 1 for ``reset_sequences`` tests; the ticket sequence is not one, so
    such a reset neither fails nor hands out a number below 1001."""

    reset_sequences = True

    def test_resetting_the_databases_sequences_leaves_ticket_numbers_alone(self):
        self.assertGreaterEqual(new_ticket().number, numbering.FIRST_NUMBER)


class StaffActionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()
        self.ticket = new_ticket(participants=["pat@example.org"])

    def kinds(self, ticket=None):
        return list((ticket or self.ticket).events.order_by("created_at").values_list("kind", flat=True))

    def test_each_field_change_is_recorded_once(self):
        category = TicketCategory.objects.create(name="Registration")

        changed = tickets.update_ticket(
            self.ticket,
            actor=self.agent,
            status=Status.RESOLVED,
            priority="high",
            category=category,
            assignee=self.agent,
        )
        unchanged = tickets.update_ticket(self.ticket, actor=self.agent, status=Status.RESOLVED, priority="high")

        self.ticket.refresh_from_db()
        self.assertEqual(changed, ["status", "priority", "category", "assignee"])
        self.assertEqual(unchanged, [])
        self.assertEqual(
            (self.ticket.status, self.ticket.priority, self.ticket.category, self.ticket.assignee),
            (Status.RESOLVED, "high", category, self.agent),
        )
        self.assertIsNotNone(self.ticket.closed_at)
        self.assertIsNotNone(self.ticket.resolved_at)
        self.assertEqual(self.kinds(), [Kind.STATUS, Kind.PRIORITY, Kind.CATEGORY, Kind.ASSIGNED])
        assigned = self.ticket.events.get(kind=Kind.ASSIGNED)
        self.assertEqual((assigned.actor, assigned.data), (self.agent, {"from": "", "to": "Avery Agent"}))

    def test_reopening_clears_the_close_times(self):
        tickets.update_ticket(self.ticket, actor=self.agent, status=Status.CLOSED)
        tickets.update_ticket(self.ticket, actor=self.agent, status=Status.OPEN)

        self.ticket.refresh_from_db()
        self.assertEqual((self.ticket.closed_at, self.ticket.resolved_at), (None, None))

    def test_a_note_is_internal_scrubbed_and_recorded(self):
        note = tickets.add_note(self.ticket, actor=self.agent, body=f"  Called them. Link: {corpus.LOGIN_LINK}  ")

        self.assertEqual((note.kind, note.author, note.from_name), (TicketMessage.Kind.NOTE, self.agent, "Avery Agent"))
        self.assertEqual(note.body_text, "Called them. Link: [sign-in link removed]")
        self.assertEqual(self.kinds(), [Kind.NOTE])
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.last_activity_at, note.occurred_at)

    def test_bulk_status_assignment_and_read(self):
        other = new_ticket(unread=True)

        self.assertEqual(tickets.set_status([self.ticket, other], Status.CLOSED, actor=self.agent), 2)
        self.assertEqual(tickets.assign([self.ticket], self.agent, actor=self.agent), 1)
        self.assertEqual(tickets.mark_read([self.ticket, other]), 1)
        other.refresh_from_db()
        self.assertFalse(other.unread)

    def test_spam_and_moving_automated_mail_to_the_queue(self):
        automated = new_ticket(
            automated=True, status=Status.CLOSED, classification="auto_reply", closed_at=timezone.now()
        )
        merged = new_ticket(status=Status.MERGED)

        self.assertEqual(tickets.mark_spam([self.ticket, merged], actor=self.agent), 1)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, Status.SPAM)
        self.assertEqual(self.kinds()[-1], Kind.SPAM)

        self.assertEqual(tickets.move_to_queue([automated, self.ticket, merged], actor=self.agent), 2)
        automated.refresh_from_db()
        self.assertEqual(
            (automated.automated, automated.status, automated.closed_at, automated.unread),
            (False, Status.OPEN, None, True),
        )
        self.assertEqual(automated.events.get(kind=Kind.RECLASSIFIED).data, {"from": "auto_reply", "to": "human"})

    def test_merging_moves_everything_into_the_oldest_ticket(self):
        reader = FakeReader()
        first = receive(corpus.message(message_id="<a@x>"), reader=reader)
        second = receive(corpus.message(message_id="<b@x>", sender="kim@example.org"), reader=reader)
        tickets.add_note(second, actor=self.agent, body="note")

        target = tickets.merge([second, first], actor=self.agent)

        second.refresh_from_db()
        self.assertEqual(target.pk, first.pk)
        self.assertEqual(target.messages.count(), 3)
        self.assertEqual((second.status, second.merged_into), (Status.MERGED, first))
        self.assertIsNotNone(second.closed_at)
        first.refresh_from_db()
        self.assertEqual(set(first.participants), {"pat@example.org", "kim@example.org"})
        self.assertEqual(first.events.get(kind=Kind.MERGED).data, {"source": second.number, "messages": 2})
        self.assertEqual(second.events.get(kind=Kind.MERGED).data, {"into": first.number})
        self.assertIsNone(tickets.merge([first], actor=self.agent))
        self.assertIsNone(tickets.merge([first, second], actor=self.agent))

    def test_only_staff_with_the_helpdesk_grant_can_be_assigned(self):
        master = make_superuser(email="master@example.com")
        make_admin(apps=["mail"], email="mailer@example.com")

        self.assertEqual({member.pk for member in tickets.helpdesk_staff()}, {self.agent.pk, master.pk})


class RetentionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.now = timezone.now()

    def message(self, ticket, kind=TicketMessage.Kind.CUSTOMER, *, age_days=0, with_file=True):
        message = TicketMessage.objects.create(
            ticket=ticket,
            kind=kind,
            occurred_at=self.now - timedelta(days=age_days),
            body_text="text",
            body_html="<p>html</p>",
            attached_messages=[{"text": "x"}],
        )
        if with_file:
            TicketAttachment.objects.create(message=message, filename="a.pdf", content=b"%PDF", size=4)
        return message

    def test_each_retention_period(self):
        settings = HelpdeskSettings.objects.create(
            automated_retention_days=90,
            spam_retention_days=30,
            closed_body_retention_days=730,
            attachment_retention_days=365,
            ticket_retention_days=1095,
        )
        automated = self.message(
            new_ticket(automated=True, status=Status.CLOSED, closed_at=self.now),
            TicketMessage.Kind.AUTOMATED,
            age_days=91,
        )
        fresh_automated = self.message(new_ticket(automated=True), TicketMessage.Kind.AUTOMATED, age_days=10)
        spam = self.message(new_ticket(status=Status.SPAM, closed_at=self.now), age_days=31)
        long_closed = self.message(new_ticket(status=Status.CLOSED, closed_at=self.now - timedelta(days=731)))
        files_only = self.message(new_ticket(status=Status.RESOLVED, closed_at=self.now - timedelta(days=366)))
        open_ticket = self.message(new_ticket(), age_days=2000)
        expired = new_ticket(status=Status.CLOSED, closed_at=self.now - timedelta(days=1096))
        self.message(expired, with_file=False)

        result = retention.purge_expired(now=self.now)

        self.assertEqual(
            result, {"automated_bodies": 1, "spam_bodies": 1, "closed_bodies": 2, "attachments": 1, "tickets": 1}
        )
        for message in (automated, spam, long_closed):
            message.refresh_from_db()
            self.assertEqual((message.body_text, message.body_html, message.attached_messages), ("", "", []))
            self.assertEqual(message.body_purged_at, self.now)
            self.assertIsNone(message.attachments.get().content)
        files_only.refresh_from_db()
        self.assertEqual(files_only.body_text, "text")
        self.assertIsNone(files_only.attachments.get().content)
        for kept in (fresh_automated, open_ticket):
            kept.refresh_from_db()
            self.assertEqual(kept.body_text, "text")
            self.assertEqual(bytes(kept.attachments.get().content), b"%PDF")
        self.assertFalse(Ticket.objects.filter(pk=expired.pk).exists())
        self.assertEqual(retention.purge_expired(now=self.now), dict.fromkeys(result, 0))
        self.assertTrue(settings.pk)

    def test_a_stop_request_ends_the_purge(self):
        self.message(new_ticket(status=Status.SPAM), age_days=400)

        self.assertEqual(sum(retention.purge_expired(now=self.now, should_stop=lambda: True).values()), 0)


class EventDescriptionTests(TestCase):
    def test_every_kind_reads_as_one_line(self):
        ticket = new_ticket()
        samples = {
            Kind.CREATED: ({"automated": True}, "Ticket opened as automated mail (closed at once)"),
            Kind.CUSTOMER_MESSAGE: (
                {"from": "pat@example.org", "rule": "references"},
                "Customer message from pat@example.org (threaded by its In-Reply-To / References)",
            ),
            Kind.AUTOMATED_MESSAGE: ({"rule": "new"}, "Automated message attached from unknown sender"),
            Kind.STATUS: (
                {"from": "new", "to": "open", "reason": "the customer replied"},
                "Status changed: New → Open (the customer replied)",
            ),
            Kind.REOPENED: ({"from": "closed", "to": "open"}, "Reopened: Closed → Open"),
            Kind.PRIORITY: ({"from": "normal", "to": "urgent"}, "Priority: Normal → Urgent"),
            Kind.ASSIGNED: ({"from": "", "to": "Avery Agent"}, "Assignee changed: — → Avery Agent"),
            Kind.MERGED: ({"into": 1005}, "Merged into I2G-#1005"),
            Kind.RELATED: ({"number": 1007}, "Related ticket: I2G-#1007 (same conversation)"),
            Kind.MENTION: (
                {"number": 1009},
                "The message names I2G-#1009, but its sender is not a participant of that ticket",
            ),
            Kind.FLOOD: (
                {"from": "pat@example.org"},
                "Grouped into this ticket: many new tickets from pat@example.org",
            ),
            Kind.SPAM: ({}, "Marked as spam"),
        }
        for kind, (data, expected) in samples.items():
            with self.subTest(kind):
                self.assertEqual(events.describe(events.record(ticket, kind, **data)), expected)
        merged_in = events.record(ticket, Kind.MERGED, source=1004, messages=2)
        self.assertEqual(events.describe(merged_in), "I2G-#1004 merged into this ticket (2 messages moved)")
        self.assertEqual(events.describe(events.record(ticket, Kind.CREATED)), "Ticket opened")


class ModelTests(TestCase):
    def test_strings_and_helpers(self):
        ticket = new_ticket(subject="")
        message = TicketMessage.objects.create(ticket=ticket, kind="note", occurred_at=timezone.now())
        attachment = TicketAttachment.objects.create(message=message, filename="a.txt")

        self.assertEqual(str(ticket), f"I2G-#{ticket.number}: (no subject)")
        self.assertTrue(ticket.is_open)
        self.assertIn("Internal note", str(message))
        self.assertEqual((str(attachment), attachment.stored), ("a.txt", False))
        self.assertEqual(str(TicketCategory(name="Billing")), "Billing")
        self.assertIn("Ticket created", str(events.record(ticket, Kind.CREATED)))
        self.assertEqual(str(HelpdeskSettings()), "Helpdesk Settings")

    def test_settings_load_defaults_until_saved(self):
        defaults = HelpdeskSettings.load()
        self.assertTrue(defaults._state.adding)  # unsaved (a UUID primary key is assigned on creation)
        self.assertFalse(HelpdeskSettings.objects.exists())
        self.assertEqual((defaults.enabled, defaults.shadow_mode, defaults.reopen_window_days), (True, True, 14))

        saved = HelpdeskSettings.objects.create(reopen_window_days=3)
        self.assertEqual(HelpdeskSettings.load().pk, saved.pk)

    def test_the_ingest_record_is_a_view_of_the_inbound_queue(self):
        row = InboundMessage.objects.create(mailbox="i2g@ucmerced.edu", graph_id="g", received_at=timezone.now())

        self.assertEqual(IngestRecord.objects.get().pk, row.pk)
        self.assertTrue(IngestRecord._meta.proxy)
        self.assertEqual(IngestRecord._meta.app_label, "helpdesk")
