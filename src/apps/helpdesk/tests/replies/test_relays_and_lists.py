"""Web forms and mailing lists: whom the ticket belongs to (``ingest.routing.people``).

- A relay is never taken for the people it relays: form submissions that share a Graph conversation (one subject,
  one form) open a ticket each, while the same person writing again joins their own; so does a nameless submission
  after the form's ticket was merged into a person's ticket.
- Moving list mail or a relayed message to the queue gives the ticket to the person who wrote it, with their name (a
  form's person, a list's poster: its Reply-To, X-Original-From or Cc), listed as a participant, and the timeline
  says so. A mailing list's own address (its List-Post; without one, its Reply-To) never is the requester nor a
  participant; a reply never goes to it, nor copies it.
- After a move only the misjudged messages become the requester's: their own out-of-office stays automated, and the
  reply quotes their question; a web form's message is quoted as its person's."""

from django.core.cache import cache
from django.test import TestCase, override_settings

from ...models import Ticket, TicketEvent, TicketMessage
from ...services import outbound, tickets
from ...services.outbound.replies import ReplyRefused, last_inbound, parse_cc
from ...services.tickets import events
from .. import corpus
from ..helpers import helpdesk_staff, receive
from ..helpers.service import sending_settings
from ..service.intake.scam_mail import DMARC_PASS, locked_out

Kind = TicketMessage.Kind
FORM = "Website Contact Form <webform@forms.example>"
LIST = "faculty-list@lists.example.edu"
LIST_HEADERS = {"List-Id": "Faculty <faculty-list.lists.example.edu>", "List-Post": f"<mailto:{LIST}>"}
IRA = "Ira Moss <ira.moss@example.edu>"


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
        vic = receive(submission("Vic One <vic.one@example.org>", "Parking passes?", 1), conversation=conversation)
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
        self.assertEqual((spam.requester_email, spam.requester_name), ("uma.user@example.org", "Uma User"))
        self.assertEqual(last_inbound(spam), spam.messages.get())  # the form's message is quoted as Uma's
        moved = spam.events.get(kind=TicketEvent.Kind.RECLASSIFIED)
        self.assertEqual(
            events.describe(moved),
            "Moved to the queue; its requester is now uma.user@example.org, who wrote it (through a web form or a "
            "mailing list)",
        )

    def test_a_nameless_submission_never_joins_the_person_a_form_ticket_was_merged_into(self):
        quinn = receive(corpus.message(sender="Quinn Park <quinn@example.org>", message_id="<quinn@x>"))
        xavier = receive(submission("Xavier Three <xavier@example.org>", "Parking?", 6), conversation="AAQk-m")
        tickets.merge([quinn, xavier], actor=self.agent)
        nameless = submission("", "Can students watch the judging?", 7).replace(b"Reply-To: \r\n", b"")

        self.assertNotEqual(receive(nameless, conversation="AAQk-m").pk, quinn.pk)
        quinn.refresh_from_db()
        self.assertNotIn("webform@forms.example", outbound.cc_suggestions(quinn))

    def test_a_reply_to_the_message_was_also_sent_to_leaves_the_sender_the_requester(self):
        # A person writing to the site and their team, asking for replies to the team (an address of the message).
        raw = corpus.message(
            sender="Pat Doe <pat.doe@example.edu>",
            to=f"{corpus.SITE}, team@example.edu",
            message_id="<team-1@x>",
            headers={"Reply-To": "team@example.edu", "Authentication-Results": DMARC_PASS},
        )

        self.assertEqual(receive(raw).requester_email, "pat.doe@example.edu")

    def test_a_web_forms_message_is_quoted_as_its_persons(self):
        ticket = receive(submission("Pat Requester <pat.requester@example.org>", "When does it start?", 5))

        self.assertEqual(last_inbound(ticket), ticket.messages.get())


@override_settings(BACKGROUND_JOBS_ENABLED=True)
class ListTests(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()
        self.settings = sending_settings()

    def moved(self, sender, number, to=LIST, listing=LIST_HEADERS, **headers):
        raw = corpus.message(
            sender=sender, to=to, message_id=f"<list-{number}@lists.example.edu>", headers={**listing, **headers}
        )
        ticket = receive(raw)
        self.assertTrue(ticket.automated)
        tickets.move_to_queue([ticket], actor=self.agent)
        ticket.refresh_from_db()
        return ticket

    def test_list_mail_rewriting_its_poster_belongs_to_the_poster_once_moved(self):
        found = {
            "Reply-To the poster": self.moved(f"Pat Doe via Faculty List <{LIST}>", 1, **{"Reply-To": IRA}),
            "Mailman, the poster in Cc": self.moved(
                f"Ira Moss via Faculty List <{LIST}>", 2, **{"Reply-To": LIST, "Cc": IRA}
            ),
            "Google Groups": self.moved(
                f"'Ira Moss' via Faculty <{LIST}>", 3, **{"Reply-To": LIST, "X-Original-From": IRA}
            ),
        }
        for case, ticket in found.items():
            with self.subTest(case):
                self.assertEqual((ticket.requester_name, ticket.requester_email), ("Ira Moss", "ira.moss@example.edu"))
                self.assertNotIn(LIST, ticket.participants)
                self.assertIn("ira.moss@example.edu", ticket.participants)
                self.assertEqual(outbound.can_reply(ticket, self.settings), "")
                self.assertNotIn("alias", ticket.events.get(kind=TicketEvent.Kind.RECLASSIFIED).data)  # the list's

    def test_a_list_asking_for_replies_to_itself_leaves_the_poster_the_requester(self):
        unposted = {"List-Id": LIST_HEADERS["List-Id"], "Precedence": "list"}  # no List-Post: its Reply-To is the list
        cases = ((4, LIST, LIST_HEADERS), (5, corpus.SITE, LIST_HEADERS), (8, corpus.SITE, unposted))
        for number, to, listing in cases:  # sent To the list, or to each member (personal delivery)
            with self.subTest(to=to, listing=listing):
                ticket = self.moved(IRA, number, to=to, listing=listing, **{"Reply-To": LIST})

                self.assertEqual(ticket.requester_email, "ira.moss@example.edu")
                self.assertNotIn("requester", ticket.events.get(kind=TicketEvent.Kind.RECLASSIFIED).data)
                # A participant from before the list was known as one (or a merge) is still never offered as a Cc.
                Ticket.objects.filter(pk=ticket.pk).update(participants=[*ticket.participants, LIST])
                ticket.refresh_from_db()
                self.assertNotIn(LIST, outbound.cc_suggestions(ticket))
                with self.assertRaisesMessage(ReplyRefused, f"{LIST} is a mailing list"):
                    parse_cc(LIST, ticket)

    def test_list_mail_from_its_poster_is_theirs_whatever_its_reply_to(self):
        raw = corpus.message(
            sender=f"Gil Moss via Faculty <{LIST}>",
            to=LIST,
            message_id="<gg@x>",
            headers={**LIST_HEADERS, "X-Original-From": IRA},
        )
        self.assertIn("ira.moss@example.edu", receive(raw).participants)  # the poster, while the ticket is the list's
        organizer = self.moved(IRA, 9, to=corpus.SITE, **{"Reply-To": "Organizer <org@example.edu>"})

        self.assertEqual(organizer.requester_email, "ira.moss@example.edu")

    def test_a_list_that_hides_its_poster_is_never_replied_to_nor_copied(self):
        ticket = self.moved(f"Faculty List <{LIST}>", 6, **{"Reply-To": LIST})

        self.assertEqual(ticket.requester_email, LIST)
        self.assertIn(
            "is a mailing list: a reply would reach all its members", outbound.can_reply(ticket, self.settings)
        )
        with self.assertRaisesMessage(ReplyRefused, f"{LIST} is a mailing list"):
            parse_cc(LIST, ticket)

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
