"""Moving misclassified mail to the queue makes it a person's ticket in full (after the third live check of the
admin): classified as a person's, the requester's messages theirs again (shown as the requester's, quoted under a
reply) and, when the scam checks scored them, flagged suspicious rather than spam; another sender's automated mail on
the ticket stays as it was."""

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from ...models import Ticket, TicketMessage
from ...services import tickets
from ...services.outbound.replies import last_inbound
from .. import corpus
from ..helpers import helpdesk_staff, receive
from ..service.intake.scam_mail import locked_out

Status = Ticket.Status
Kind = TicketMessage.Kind


class MovedToQueueTests(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()
        self.client.force_login(self.agent)

    def moved(self, ticket):
        self.assertEqual(tickets.move_to_queue([ticket], actor=self.agent), 1)
        ticket.refresh_from_db()
        return ticket

    def test_mail_the_scam_checks_made_spam_becomes_the_requesters_suspicious_message(self):
        spam = receive(locked_out())
        self.assertEqual((spam.status, spam.classification), (Status.SPAM, "spam"))

        ticket = self.moved(spam)

        message = ticket.messages.get()
        self.assertEqual((ticket.classification, ticket.flags, ticket.automated), ("human", ["suspicious"], False))
        self.assertEqual((message.kind, message.classification, message.scam_level), (Kind.CUSTOMER, "human", "medium"))
        self.assertEqual(last_inbound(ticket), message)  # quoted under the first reply
        page = self.client.get(reverse("admin:helpdesk_ticket_change", args=[ticket.pk]))
        self.assertContains(page, "Suspicious: the scam checks found warning signs.")
        self.assertNotContains(page, "Marked as spam by the scam checks.")

    def test_mail_exchange_rated_spam_is_not_flagged(self):
        ticket = self.moved(receive(corpus.spam()))

        message = ticket.messages.get()
        self.assertEqual((message.kind, message.classification, message.scam_level), (Kind.CUSTOMER, "human", ""))
        self.assertEqual((ticket.classification, ticket.flags), ("human", []))

    def test_another_senders_automated_mail_stays_automated(self):
        spam = receive(locked_out())
        reply = corpus.out_of_office(sender="Kim Lee <kim@example.org>", in_reply_to="<locked-1@mail.example.org>")
        self.assertEqual(receive(reply).pk, spam.pk)

        ticket = self.moved(spam)

        kinds = dict(ticket.messages.values_list("from_address", "kind"))
        self.assertEqual(kinds, {"pat@example.org": Kind.CUSTOMER, "kim@example.org": Kind.AUTOMATED})
