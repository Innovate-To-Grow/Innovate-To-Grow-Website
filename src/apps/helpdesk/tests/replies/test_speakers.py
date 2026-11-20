"""Whom a message speaks for, after the fifth live check of the admin (``ingest.routing.people``):

- a requester answering under the ticket number with a Reply-To naming someone else (an assistant, a home address)
  still reaches their ticket, Exchange-rated spam included; a relay that wrote there for someone else never does,
  with or without a Reply-To, so a form's next submission opens a ticket of its own;
- a web form that copies its submitter (Cc) still gives the ticket to them, and is never acknowledged;
- a person whose Reply-To is their other address (the same name) keeps their member link, threads from either
  address, and is quoted from their latest message that says something (never an answer that only quotes);
- the reply form suggests people only as Cc, never a relay or a no-reply address."""

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.authn.models import ContactEmail, Member

from ...models import Ticket, TicketMessage
from ...services import outbound, tickets
from ...services.outbound.replies import last_inbound
from .. import corpus
from ..helpers import helpdesk_staff, receive
from ..helpers.service import sending_settings
from ..service.intake.scam_mail import DMARC_PASS

Status = Ticket.Status
Kind = TicketMessage.Kind
FORM = "Website Contact Form <webform@forms.example>"
PASS = {"Authentication-Results": DMARC_PASS}


def answer(ticket, sender, *, text="Please also copy my office on the briefing details.", number=2, **headers):
    raw = corpus.message(
        sender=sender,
        subject=f"Re: {ticket.subject} [{ticket.display_number}]",
        text=text,
        message_id=f"<answer-{number}@example.org>",
        headers=headers,
    )
    return receive(raw)


class AnswerTests(TestCase):
    def setUp(self):
        cache.clear()
        self.ticket = receive(corpus.message(sender="Riley Chen <riley@example.org>", message_id="<riley-1@x>"))
        tickets.update_ticket(self.ticket, actor=helpdesk_staff(), status=Status.PENDING_CUSTOMER)
        Ticket.objects.filter(pk=self.ticket.pk).update(unread=False)

    def test_an_answer_naming_someone_else_in_reply_to_joins_the_requesters_ticket(self):
        office = answer(
            self.ticket, "Riley Chen <riley@example.org>", **{"Reply-To": "Riley Office <office@example.org>"}
        )
        home = answer(self.ticket, "Riley Chen <riley@example.org>", number=3, **{"Reply-To": "riley@home.example"})

        self.assertEqual((office.pk, home.pk), (self.ticket.pk, self.ticket.pk))
        self.ticket.refresh_from_db()
        self.assertEqual((self.ticket.status, self.ticket.unread), (Status.OPEN, True))
        self.assertTrue({"office@example.org", "riley@home.example"} <= set(self.ticket.participants))

    def test_an_answer_exchange_rates_spam_with_a_reply_to_joins_too_warned(self):
        headers = {"Reply-To": "Riley Office <office@example.org>", "X-MS-Exchange-Organization-SCL": "5"}

        joined = answer(self.ticket, "Riley Chen <riley@example.org>", **headers)

        message = joined.messages.get(internet_message_id="<answer-2@example.org>")
        self.assertEqual(
            (joined.pk, message.kind, message.scam_reasons),
            (self.ticket.pk, Kind.CUSTOMER, ["Exchange rated it spam (SCL 5)"]),
        )


@override_settings(BACKGROUND_JOBS_ENABLED=True)
class RelayTests(TestCase):
    def setUp(self):
        cache.clear()
        sending_settings(send_acknowledgement=True)

    def submit(self, number, *, sender=FORM, conversation="", **headers):
        raw = corpus.message(
            sender=sender,
            subject="New contact form submission",
            text=f"Message {number}",
            message_id=f"<form-{number}@forms.example>",
            headers={**PASS, **headers},
        )
        with self.captureOnCommitCallbacks(execute=True):
            return receive(raw, conversation=conversation)

    def test_a_form_copying_its_submitter_gives_them_the_ticket_and_no_acknowledgement(self):
        xena = self.submit(1, **{"Cc": "Xena Copy <xena@example.org>", "Reply-To": "Xena Copy <xena@example.org>"})
        yuri = self.submit(
            2,
            sender="Website Form <no-reply@webforms.example>",
            **{"Cc": "yuri@example.org", "Reply-To": "yuri@example.org"},
        )

        self.assertEqual((xena.requester_name, xena.requester_email), ("Xena Copy", "xena@example.org"))
        self.assertFalse(xena.messages.filter(kind=Kind.REPLY, automatic=True).exists())
        self.assertEqual((yuri.automated, yuri.requester_email), (False, "yuri@example.org"))

    def test_a_submission_without_a_reply_to_never_joins_another_persons_ticket(self):
        xavier = self.submit(3, conversation="AAQk-form", **{"Reply-To": "Xavier Three <xavier@example.org>"})
        anonymous = self.submit(4, conversation="AAQk-form")
        again = self.submit(5, conversation="AAQk-form", **{"Reply-To": "Xavier Three <xavier@example.org>"})

        self.assertNotEqual(anonymous.pk, xavier.pk)
        self.assertEqual(again.pk, xavier.pk)

    def test_the_reply_form_suggests_people_only_as_cc(self):
        ticket = self.submit(6, **{"Reply-To": "Robin Person <robin@example.org>", "Cc": "Kim Lee <kim@example.org>"})
        quiet = self.submit(
            7, sender="no-reply@webforms.example", **{"Reply-To": "sam@example.org", "Cc": "kim@example.org"}
        )

        copied = self.submit(
            8, sender="Pat Doe <pat@example.org>", **{"Cc": "noreply@service.example, kim@example.org"}
        )

        self.assertEqual(outbound.cc_suggestions(ticket), ["kim@example.org"])
        self.assertEqual(outbound.cc_suggestions(quiet), ["kim@example.org"])
        self.assertIn("noreply@service.example", copied.participants)  # it threads, but is never offered as a Cc
        self.assertEqual(outbound.cc_suggestions(copied), ["kim@example.org"])


class AliasTests(TestCase):
    def setUp(self):
        cache.clear()
        self.dana = Member.objects.create_user(password="x", first_name="Dana", last_name="Member")
        ContactEmail.objects.create(member=self.dana, email_address="dana@example.com", email_type="primary")
        raw = corpus.message(
            sender="Dana Member <dana@example.com>",
            message_id="<dana-1@x>",
            headers={**PASS, "Reply-To": "Dana Member <dana@home.example>"},
        )
        self.ticket = receive(raw)

    def test_a_reply_to_her_other_address_keeps_her_member_link_and_both_addresses_thread(self):
        joined = answer(self.ticket, "Dana Member <dana@example.com>", text="And one more question.")

        self.assertEqual((self.ticket.requester_email, self.ticket.requester_member), ("dana@home.example", self.dana))
        self.assertEqual(joined.pk, self.ticket.pk)
        self.assertEqual(last_inbound(joined).internet_message_id, "<answer-2@example.org>")

    def test_an_answer_that_only_quotes_is_never_quoted_back(self):
        quoted = "On Wed, Nov 11, 2026 at 10:00 AM Innovate to Grow wrote:\n> Hello Dana, yes: the room is booked."
        answer(self.ticket, "Dana Member <dana@example.com>", text=quoted)

        self.assertEqual(last_inbound(self.ticket).internet_message_id, "<dana-1@x>")
