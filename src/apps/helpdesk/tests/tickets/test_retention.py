from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.core.models import InboundMessage
from apps.helpdesk.tests.tickets.test_tickets import Kind, Status, new_ticket

from ...models import HelpdeskSettings, IngestRecord, Ticket, TicketAttachment, TicketCategory, TicketMessage
from ...services.outbound import jobs
from ...services.tickets import events, retention


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
                "Status changed: New → In progress (the customer replied)",
            ),
            Kind.REOPENED: ({"from": "closed", "to": "open"}, "Reopened: Closed → In progress"),
            Kind.PRIORITY: ({"from": "normal", "to": "urgent"}, "Priority: 3 – Moderate → 1 – Critical"),
            Kind.IMPACT: ({"from": "2 – Medium", "to": "1 – High"}, "Impact: 2 – Medium → 1 – High"),
            Kind.URGENCY: ({"from": "3 – Low", "to": "2 – Medium"}, "Urgency: 3 – Low → 2 – Medium"),
            Kind.GROUP: ({"from": "", "to": "Events"}, "Assignment group changed: — → Events"),
            Kind.RESOLUTION: ({"code": "solved", "notes": True}, "Resolution: Solved (notes updated)"),
            Kind.REPLY: ({"to": "pat@example.org"}, "Reply sent to pat@example.org"),
            Kind.ACKNOWLEDGED: ({"to": "pat@example.org"}, "Acknowledgement sent to pat@example.org"),
            Kind.REPLY_FAILED: (
                {"what": "reply", "error": "Could not be sent."},
                "The reply was not sent: Could not be sent.",
            ),
            Kind.NOTIFIED: ({"reason": "group", "count": 3}, "Assignment notice emailed to the group's 3 members"),
            Kind.RESPONDED: ({"by": "reply"}, "First response: a reply was sent"),
            Kind.SLA_BREACHED: ({"which": "response"}, "SLA breached: the response is overdue"),
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

    def test_the_variants_of_one_kind(self):
        ticket = new_ticket()
        shadow = "Not sent: shadow mode was switched on before it went out."
        samples = (
            (Kind.NOTIFIED, {"reason": "assigned", "count": 1}, "Assignment notice emailed to the assignee"),
            (Kind.NOTIFIED, {"reason": "group", "count": 1}, "Assignment notice emailed to the group's 1 member"),
            (
                Kind.REPLY_FAILED,
                {"what": "reply", "error": shadow},
                "The reply was not sent: shadow mode was switched on before it went out.",
            ),
            (Kind.REPLY_FAILED, {"what": "acknowledgement"}, "The acknowledgement was not sent: delivery failed"),
            (
                Kind.REPLY_FAILED,
                {"what": "reply", "error": jobs.UNCERTAIN_ERROR, "uncertain": True},
                f"The reply may not have been delivered: {jobs.UNCERTAIN_ERROR}",
            ),
            (Kind.RESOLUTION, {"cleared": "solved"}, "Resolution cleared on reopening (was: Solved)"),
            (Kind.MERGED, {"source": 1004, "messages": 1}, "I2G-#1004 merged into this ticket (1 message moved)"),
        )
        for kind, data, expected in samples:
            with self.subTest(kind=kind, data=data):
                self.assertEqual(events.describe(events.record(ticket, kind, **data)), expected)


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
