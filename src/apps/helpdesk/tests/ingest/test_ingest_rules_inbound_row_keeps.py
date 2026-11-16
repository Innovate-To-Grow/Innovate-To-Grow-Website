from django.utils import timezone

from apps.core.models import InboundMessage
from apps.helpdesk.tests.ingest.test_ingest_rules import Kind, Status, _AutomatedMailCase, event_kinds

from ...models import Ticket, TicketMessage
from ...services.ingest.pipeline.messages import OWN_MAIL_NOTE
from .. import corpus
from ..helpers import FakeReader, ingest, queue, receive


class AutomatedMailTests(_AutomatedMailCase):
    def test_the_inbound_row_keeps_the_class_for_other_tools(self):
        reader = FakeReader()
        row = queue(corpus.left_organisation(), reader=reader)
        ingest(reader)

        row.refresh_from_db()
        self.assertEqual(
            (row.status, row.classification, row.subtype), (InboundMessage.Status.DONE, "left_org", "left_org")
        )
        self.assertTrue(row.result["created"])

    def test_the_sites_own_mail_keeps_no_content(self):
        raw = corpus.message(
            sender="Innovate to Grow <i2g@ucmerced.edu>",
            text="Your code is 123456",
            html="<p>Your code is 123456</p>",
            headers={"X-MS-Exchange-Organization-AuthAs": "Internal"},
            attachments=[("ticket.pdf", b"%PDF-1.7", "application/pdf")],
        )

        message = receive(raw).messages.get()

        self.assertEqual((message.body_text, message.body_html), (OWN_MAIL_NOTE, ""))
        self.assertFalse(message.attachments.exists())
        self.assertEqual(message.attached_messages, [])

    def test_automated_mail_keeps_no_text_of_the_messages_it_returns(self):
        raw = corpus.message(
            sender="MAILER-DAEMON <mailer-daemon@mx.example.org>",
            subject="Undelivered Mail Returned to Sender",
            message_id="<ndr-2@mx.example.org>",
        )
        ticket = receive(raw)

        self.assertEqual(ticket.classification, "bounce")
        self.assertEqual(ticket.messages.get().attached_messages, [])

    def test_automated_mail_joins_its_thread_without_changing_the_ticket(self):
        reader = FakeReader()
        human = receive(corpus.message(sender="Alex Kim <alex.kim@contoso.example>"), reader=reader)
        Ticket.objects.filter(pk=human.pk).update(status=Status.CLOSED, closed_at=timezone.now(), unread=False)
        before = Ticket.objects.get(pk=human.pk)

        joined = receive(corpus.out_of_office(in_reply_to="<m1@mail.example.org>"), reader=reader)

        joined.refresh_from_db()
        self.assertEqual(joined.pk, human.pk)
        self.assertEqual(
            (joined.status, joined.unread, joined.last_activity_at, joined.closed_at),
            (Status.CLOSED, False, before.last_activity_at, before.closed_at),
        )
        self.assertEqual(
            list(joined.messages.values_list("kind", flat=True)),
            [TicketMessage.Kind.CUSTOMER, TicketMessage.Kind.AUTOMATED],
        )
        self.assertEqual(event_kinds(joined), [Kind.CREATED, Kind.AUTOMATED_MESSAGE])

    def test_an_automated_ticket_never_reopens_and_a_person_gets_a_new_ticket(self):
        reader = FakeReader()
        automated = receive(corpus.out_of_office(), reader=reader)

        follow = receive(
            corpus.message(sender="Alex Kim <alex.kim@contoso.example>", in_reply_to="<oof-1@contoso.example>"),
            reader=reader,
        )

        automated.refresh_from_db()
        self.assertNotEqual(follow.pk, automated.pk)
        self.assertEqual((automated.status, automated.automated), (Status.CLOSED, True))
        self.assertEqual((follow.status, follow.related_ticket), (Status.NEW, automated))
        self.assertIn(Kind.RELATED, event_kinds(automated))
