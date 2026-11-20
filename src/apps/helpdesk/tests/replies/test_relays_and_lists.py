"""Web forms and mailing lists, after the fourth live check of the admin: whom the ticket belongs to.

- A relay is never taken for the people it relays: form submissions that share a Graph conversation (one subject,
  one form) open a ticket each, while the same person writing again joins their own.
- Moving list mail or a relayed message to the queue gives the ticket to the person its message named in Reply-To
  (the timeline says so), unless the Reply-To is an address the message was sent to: a list asking for replies to
  itself, where the sender stays the requester.
- After a move only the misjudged messages become the requester's: their own out-of-office stays automated, and the
  reply quotes their question; a web form's message is quoted as its person's."""

from django.core.cache import cache
from django.test import TestCase

from ...models import TicketEvent, TicketMessage
from ...services import tickets
from ...services.outbound.replies import last_inbound
from ...services.tickets import events
from .. import corpus
from ..helpers import helpdesk_staff, receive
from ..service.intake.scam_mail import DMARC_PASS, locked_out

Kind = TicketMessage.Kind
FORM = "Website Contact Form <webform@forms.example>"
LIST = "faculty-list@lists.example.edu"
LIST_HEADERS = {"List-Id": "Faculty <faculty.lists.example.edu>", "List-Post": f"<mailto:{LIST}>"}


def submission(person: str, text: str, number: int, **headers) -> bytes:
    headers = {"Reply-To": person, "Authentication-Results": DMARC_PASS, **headers}
    return corpus.message(
        sender=FORM,
        subject="New contact form submission",
        text=text,
        message_id=f"<form-{number}@forms.example>",
        headers=headers,
    )


class RelayTests(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()

    def test_submissions_sharing_a_conversation_are_each_their_persons_ticket(self):
        conversation = "AAQkAGI2TG93AAA="
        vic = receive(
            submission("Vic One <vic.one@example.org>", "Do judges get parking passes?", 1), conversation=conversation
        )
        wen = receive(submission("Wen Two <wen.two@example.org>", "Can I volunteer?", 2), conversation=conversation)
        again = receive(submission("Vic One <vic.one@example.org>", "And a second pass?", 3), conversation=conversation)

        self.assertNotEqual(vic.pk, wen.pk)
        self.assertEqual((vic.requester_email, wen.requester_email), ("vic.one@example.org", "wen.two@example.org"))
        self.assertEqual(again.pk, vic.pk)

    def test_a_relayed_message_moved_to_the_queue_belongs_to_its_person(self):
        raw = submission("Uma User <uma.user@example.org>", "Is the judges briefing online?", 4)
        spam = receive(raw.replace(b"\r\n\r\n", b"\r\nX-MS-Exchange-Organization-SCL: 5\r\n\r\n", 1))
        self.assertEqual((spam.classification, spam.requester_email), ("spam", "webform@forms.example"))

        tickets.move_to_queue([spam], actor=self.agent)

        spam.refresh_from_db()
        self.assertEqual((spam.requester_email, spam.requester_name), ("uma.user@example.org", ""))
        self.assertEqual(last_inbound(spam), spam.messages.get())  # the form's message is quoted as Uma's
        moved = spam.events.get(kind=TicketEvent.Kind.RECLASSIFIED)
        self.assertEqual(
            events.describe(moved),
            "Moved to the queue; its requester is now uma.user@example.org, whom its message named in Reply-To",
        )

    def test_a_reply_to_the_message_was_also_sent_to_leaves_the_sender_the_requester(self):
        # A person writing to the site and their team, asking for replies to the team (an address of the message).
        raw = corpus.message(
            sender="Pat Doe <pat.doe@example.edu>",
            to=f"{corpus.SITE}, team@example.edu",
            headers={"Reply-To": "team@example.edu", "Authentication-Results": DMARC_PASS},
            message_id="<team-1@example.edu>",
        )

        self.assertEqual(receive(raw).requester_email, "pat.doe@example.edu")

    def test_a_web_forms_message_is_quoted_as_its_persons(self):
        ticket = receive(submission("Pat Requester <pat.requester@example.org>", "When does it start?", 5))

        self.assertEqual(last_inbound(ticket), ticket.messages.get())


class ListTests(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()

    def moved(self, raw):
        ticket = receive(raw)
        self.assertTrue(ticket.automated)
        tickets.move_to_queue([ticket], actor=self.agent)
        ticket.refresh_from_db()
        return ticket

    def test_list_mail_rewriting_its_sender_belongs_to_the_person_once_moved(self):
        raw = corpus.message(
            sender=f"Pat Doe via Faculty List <{LIST}>",
            to=LIST,
            headers={"Reply-To": "Pat Doe <pat.doe@example.edu>", **LIST_HEADERS},
            message_id="<list-1@lists.example.edu>",
        )

        self.assertEqual(self.moved(raw).requester_email, "pat.doe@example.edu")

    def test_a_list_asking_for_replies_to_itself_leaves_the_sender_the_requester(self):
        raw = corpus.message(
            sender="Pat Doe <pat.doe@example.edu>",
            to=LIST,
            headers={"Reply-To": LIST, **LIST_HEADERS},
            message_id="<list-2@lists.example.edu>",
        )

        ticket = self.moved(raw)

        self.assertEqual(ticket.requester_email, "pat.doe@example.edu")
        self.assertNotIn("requester", ticket.events.get(kind=TicketEvent.Kind.RECLASSIFIED).data)

    def test_the_requesters_out_of_office_stays_automated_and_is_never_quoted(self):
        spam = receive(locked_out())
        reply = corpus.out_of_office(
            sender="Pat Doe <pat@example.org>", in_reply_to="<locked-1@mail.example.org>", message_id="<oof-pat@x>"
        )
        self.assertEqual(receive(reply).pk, spam.pk)

        tickets.move_to_queue([spam], actor=self.agent)

        kinds = dict(spam.messages.values_list("internet_message_id", "kind"))
        self.assertEqual(kinds, {"<locked-1@mail.example.org>": Kind.CUSTOMER, "<oof-pat@x>": Kind.AUTOMATED})
        self.assertEqual(last_inbound(spam).internet_message_id, "<locked-1@mail.example.org>")
