"""Whom a message speaks for, after the fifth and sixth live checks of the admin (``ingest.routing.people``):

- anyone who wrote on a ticket answers it under its number, whatever Reply-To they add: a requester naming an
  assistant or a home address (Exchange-rated spam included; she still answers in the conversation then), a sender
  whose first message named their assistant, a delegate, a team mailbox, a nameless other address;
- one form's submissions never join each other's tickets by their shared conversation: without a Reply-To, or from
  a form that names each submitter; a form's own address is never acknowledged;
- a web form that copies its submitter (Cc) still gives the ticket to them;
- a person whose Reply-To is their other address (the same name) keeps their member link, threads from either
  address (in the conversation also when their mail program shows the name differently: "Rhea", "Stone, Rhea"), and
  is quoted from their latest message that says something (never an answer that only quotes);
- the reply form suggests people only as Cc: never a relay or a no-reply address, but a sender who answered."""

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.authn.models import ContactEmail, Member

from ...models import Ticket, TicketMessage
from ...services import outbound, tickets
from ...services.ingest.routing import people
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
    subject = f"Re: {ticket.subject} [{ticket.display_number}]"
    return receive(
        corpus.message(sender=sender, subject=subject, text=text, message_id=f"<answer-{number}@x>", headers=headers)
    )


def opened(sender, reply_to, number):
    raw = corpus.message(sender=sender, message_id=f"<opened-{number}@x>", headers={**PASS, "Reply-To": reply_to})
    return receive(raw)


class AnswerTests(TestCase):
    def setUp(self):
        cache.clear()
        self.ticket = receive(corpus.message(sender="Riley Chen <riley@example.org>", message_id="<riley-1@x>"))
        tickets.update_ticket(self.ticket, actor=helpdesk_staff(), status=Status.PENDING_CUSTOMER)
        Ticket.objects.filter(pk=self.ticket.pk).update(unread=False)

    def test_an_answer_naming_someone_else_in_reply_to_joins_the_requesters_ticket(self):
        office = answer(self.ticket, "Riley Chen <riley@example.org>", **{"Reply-To": "Riley Office <office@x.org>"})
        home = answer(self.ticket, "Riley Chen <riley@example.org>", number=3, **{"Reply-To": "riley@home.example"})
        scl = answer(
            self.ticket, "riley@example.org", number=4, **{"Reply-To": "a@x.org", "X-MS-Exchange-Organization-SCL": "5"}
        )

        self.assertEqual({office.pk, home.pk, scl.pk}, {self.ticket.pk})
        self.ticket.refresh_from_db()
        self.assertEqual((self.ticket.status, self.ticket.unread), (Status.OPEN, True))
        self.assertTrue({"office@x.org", "riley@home.example"} <= set(self.ticket.participants))
        message = self.ticket.messages.get(internet_message_id="<answer-4@x>")
        self.assertEqual((message.kind, message.scam_reasons), (Kind.CUSTOMER, ["Exchange rated it spam (SCL 5)"]))

    def test_a_sender_whose_first_message_named_someone_else_answers_under_the_number(self):
        openers = {
            "an assistant": ("Kai Exec <kai@example.org>", "Mia Assistant <mia@example.org>"),
            "a delegate": ("Alex Assistant <alex@example.org>", "Bea Boss <bea@example.org>"),
            "a team mailbox": ("Sam Rivera <sam@sponsor.example>", "Sponsorship Team <team@sponsor.example>"),
            "a nameless other address": ("Nora Field <nora@example.edu>", "nora.f@home.example"),
            "her other address, then an assistant": ("Lia Moss <lia@example.edu>", "Lia Moss <lia@home.example>"),
        }
        for number, (case, (sender, reply_to)) in enumerate(openers.items()):
            with self.subTest(case):
                ticket = opened(sender, reply_to, number)
                headers = {"Reply-To": "Ana Aide <ana@example.org>"} if "then" in case else {}

                self.assertEqual(answer(ticket, sender, number=10 + number, **headers).pk, ticket.pk)

        kai = Ticket.objects.get(requester_email="mia@example.org")
        self.assertIn("kai@example.org", outbound.cc_suggestions(kai))  # he answered: a person, no relay

    def test_after_naming_her_office_the_requester_still_answers_in_the_conversation(self):
        ticket = receive(corpus.message(sender="Riley Chen <riley@example.org>", message_id="<rc@x>"), conversation="C")
        answer(ticket, "Riley Chen <riley@example.org>", number=5, **{"Reply-To": "Riley Office <office@x.org>"})
        later = corpus.message(sender="Riley Chen <riley@example.org>", subject="RE: Hello", message_id="<rc-2@x>")

        self.assertEqual(receive(later, conversation="C").pk, ticket.pk)


@override_settings(BACKGROUND_JOBS_ENABLED=True)
class RelayTests(TestCase):
    def setUp(self):
        cache.clear()
        sending_settings(send_acknowledgement=True)

    def submit(self, number, *, sender=FORM, conversation="", **headers):
        raw = corpus.message(sender=sender, subject="New contact form submission", text=f"Message {number}",
                             message_id=f"<form-{number}@forms.example>", headers={**PASS, **headers})  # fmt: skip
        with self.captureOnCommitCallbacks(execute=True):
            return receive(raw, conversation=conversation)

    def acknowledged(self, ticket):
        return ticket.messages.filter(kind=Kind.REPLY, automatic=True).exists()

    def test_a_form_copying_its_submitter_gives_them_the_ticket_and_no_acknowledgement(self):
        xena = self.submit(1, **{"Cc": "Xena Copy <xena@example.org>", "Reply-To": "Xena Copy <xena@example.org>"})
        yuri = self.submit(
            2, sender="Form <no-reply@webforms.example>", **{"Cc": "yuri@x.org", "Reply-To": "yuri@x.org"}
        )

        self.assertEqual((xena.requester_name, xena.requester_email), ("Xena Copy", "xena@example.org"))
        self.assertFalse(self.acknowledged(xena))
        self.assertEqual((yuri.automated, yuri.requester_email), (False, "yuri@x.org"))

    def test_a_submission_without_a_reply_to_never_joins_another_persons_ticket(self):
        xavier = self.submit(3, conversation="AAQk-form", **{"Reply-To": "Xavier Three <xavier@example.org>"})
        anonymous = self.submit(4, conversation="AAQk-form")
        again = self.submit(5, conversation="AAQk-form", **{"Reply-To": "Xavier Three <xavier@example.org>"})

        self.assertNotEqual(anonymous.pk, xavier.pk)
        self.assertEqual(again.pk, xavier.pk)
        self.assertFalse(self.acknowledged(anonymous))  # the form's own address, known to write for other people

    def test_a_form_naming_each_submitter_keeps_a_nameless_submission_apart(self):
        site = "wordpress@site.example"
        zed = self.submit(
            10, sender=f"Zed Alpha <{site}>", conversation="AAQk-wp", **{"Reply-To": "Zed Alpha <zed@x.org>"}
        )
        yan = self.submit(
            11, sender=f"Yan Beta <{site}>", conversation="AAQk-wp", **{"Reply-To": "Yan Beta <yan@x.org>"}
        )
        nameless = self.submit(12, sender=f"Wordpress <{site}>", conversation="AAQk-wp")
        # Under Yan's number it joins (the form wrote there), but is never quoted to Yan: it is not under her name.
        numbered = corpus.message(sender=f"Wordpress <{site}>", subject=f"Re: [{yan.display_number}]", headers=PASS)

        self.assertEqual(len({zed.pk, yan.pk, nameless.pk}), 3)
        self.assertEqual(receive(numbered.replace(b"<m1@mail", b"<wp13@mail")).pk, yan.pk)
        self.assertEqual(last_inbound(yan).internet_message_id, "<form-11@forms.example>")

    def test_the_reply_form_suggests_people_only_as_cc(self):
        ticket = self.submit(6, **{"Reply-To": "Robin Person <robin@example.org>", "Cc": "Kim Lee <kim@example.org>"})
        quiet = self.submit(7, sender="no-reply@webforms.example", **{"Reply-To": "sam@x.org", "Cc": "kim@example.org"})
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
        self.ticket = opened("Dana Member <dana@example.com>", "Dana Member <dana@home.example>", 1)

    def test_a_reply_to_her_other_address_keeps_her_member_link_and_both_addresses_thread(self):
        joined = answer(self.ticket, "Dana Member <dana@example.com>", text="And one more question.")

        self.assertEqual((self.ticket.requester_email, self.ticket.requester_member), ("dana@home.example", self.dana))
        self.assertEqual(joined.pk, self.ticket.pk)
        self.assertEqual(last_inbound(joined).internet_message_id, "<answer-2@x>")

    def test_her_answer_in_the_conversation_joins_under_another_form_of_her_name(self):
        raw = corpus.message(sender="Rhea Stone <rhea.stone@example.org>", message_id="<rhea-1@x>",
                             headers={**PASS, "Reply-To": "Rhea Stone <rhea.home@home.example>"})  # fmt: skip
        ticket = receive(raw, conversation="AAQkRHEA")

        for number, sender in enumerate(("Rhea <rhea.stone@example.org>", '"Stone, Rhea" <rhea.stone@example.org>')):
            answer = corpus.message(sender=sender, subject="RE: Easel count", message_id=f"<rhea-{number + 2}@x>")
            self.assertEqual(receive(answer, conversation="AAQkRHEA").pk, ticket.pk)
        self.assertTrue(people.same_person("Rhea", "Stone, Rhea") and people.same_person("'Rhea Stone'", "Rhea Stone"))
        self.assertFalse(people.same_person("Kim", "Kai Kim"))  # an assistant named Kim is not her boss

    def test_from_another_address_of_hers_it_is_the_requesters_answer(self):
        ContactEmail.objects.create(member=self.dana, email_address="dana@lab.example", email_type="secondary")
        tickets.update_ticket(self.ticket, actor=helpdesk_staff(), status=Status.PENDING_CUSTOMER)

        self.assertEqual(answer(self.ticket, "Dana M <dana@lab.example>").pk, self.ticket.pk)
        moved = self.ticket.events.filter(kind="status").last()
        self.assertEqual(moved.data["reason"], "the requester replied")
        self.ticket.refresh_from_db()
        self.assertIn("dana@lab.example", self.ticket.participants)
        self.assertEqual(last_inbound(self.ticket).from_address, "dana@lab.example")  # quoted, never a Cc
        self.assertNotIn("dana@lab.example", outbound.cc_suggestions(self.ticket))

    def test_an_answer_that_only_quotes_is_never_quoted_back(self):
        quoted = "On Wed, Nov 11, 2026 at 10:00 AM Innovate to Grow wrote:\n> Hello Dana, yes: the room is booked."
        answer(self.ticket, "Dana Member <dana@example.com>", text=quoted)

        self.assertEqual(last_inbound(self.ticket).internet_message_id, "<opened-1@x>")
