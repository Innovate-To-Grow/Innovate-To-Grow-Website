"""Answers on a person's ticket and mail a web form relays, after the third live check of the admin:

- a requester's answer under their ticket's number (no reply headers) is judged on what it adds: the scam checks score
  neither the staff reply it quotes ("your account has been unlocked: click here …") nor the ticket's own subject, and
  their score alone never makes an answer spam (at most suspicious), so it reaches staff: the ticket is In progress
  again and unread. A forged answer (DMARC failed) stays spam and changes nothing;
- a web form sending what someone wrote (Reply-To: that person) opens a ticket for that person, the form's address a
  participant; it gets no acknowledgement (a Reply-To is not authenticated) and a staff reply goes to the person. From
  a no-reply address it is a person's message too, never answered automatically;
- under a form ticket's number (anyone can type one into the form) a submission for someone new opens their own ticket
  (Exchange-rated spam stays spam), and one that names nobody is no requester's answer: the form, which writes for
  several people, is never offered as a Cc."""

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.core.services.email.inbound import NO_AUTO_RESPONSE

from ....models import Ticket, TicketEvent, TicketMessage
from ....services import outbound, tickets
from ... import corpus
from ...helpers import helpdesk_staff, receive
from ...helpers.service import sending_settings
from .scam_mail import DMARC_PASS

Status = Ticket.Status
Kind = TicketMessage.Kind
LEE = "Lee Kim <lee@example.org>"
QUOTED_REPLY = (
    "On Wed, Nov 11, 2026 at 10:00 AM Innovate to Grow wrote:\n"
    "> Hello Lee, your account has been unlocked. Click here on the sign-in page to reset your password within 24 "
    "hours.\n"
)


class AnswerTests(TestCase):
    def setUp(self):
        cache.clear()
        self.agent = helpdesk_staff()

    def waiting_ticket(self, subject="Cannot sign in", text="I cannot sign in to the site."):
        ticket = receive(corpus.message(sender=LEE, subject=subject, text=text, message_id="<lee-1@mail.example.org>"))
        tickets.update_ticket(ticket, actor=self.agent, status=Status.PENDING_CUSTOMER)
        Ticket.objects.filter(pk=ticket.pk).update(unread=False)
        return ticket

    def answer(self, ticket, text, *, subject="", headers=None):
        subject = subject or f"Re: {ticket.subject} [{ticket.display_number}]"
        raw = corpus.message(
            sender=LEE, subject=subject, text=text, message_id="<lee-2@mail.example.org>", headers=headers
        )
        self.assertEqual(receive(raw).pk, ticket.pk)
        ticket.refresh_from_db()
        return ticket.messages.get(internet_message_id="<lee-2@mail.example.org>")

    def assertBackInFrontOfStaff(self, ticket, message, level):
        self.assertEqual((message.kind, message.scam_level), (Kind.CUSTOMER, level))
        self.assertEqual((ticket.status, ticket.unread), (Status.OPEN, True))

    def test_the_staff_reply_it_quotes_is_not_scored(self):
        ticket = self.waiting_ticket()

        message = self.answer(ticket, f"Still not working, please help immediately.\n\n{QUOTED_REPLY}")

        self.assertBackInFrontOfStaff(ticket, message, "low")
        self.assertEqual(message.scam_reasons, [])

    def test_the_tickets_own_urgent_subject_is_not_scored_again(self):
        ticket = self.waiting_ticket(subject="URGENT: account locked, need help immediately", text="I am locked out.")

        message = self.answer(ticket, "Thanks, it works now.")

        self.assertBackInFrontOfStaff(ticket, message, "low")

    def test_an_answer_scoring_high_on_its_own_words_is_suspicious_not_spam(self):
        ticket = self.waiting_ticket()
        words = "Act now: send your password and bank account number immediately, within 24 hours, click here."

        message = self.answer(ticket, words)

        self.assertBackInFrontOfStaff(ticket, message, "medium")
        self.assertIn("Body requests personal/financial information (3 type(s))", message.scam_reasons)

    def test_a_forged_answer_stays_spam_and_changes_nothing(self):
        ticket = self.waiting_ticket()
        forged = {"Authentication-Results": "spf=fail smtp.mailfrom=example.org; dmarc=fail header.from=example.org"}

        message = self.answer(ticket, "Act now: send your password immediately, within 24 hours.", headers=forged)

        self.assertEqual((message.kind, message.classification), (Kind.AUTOMATED, "spam"))
        self.assertEqual((ticket.status, ticket.unread), (Status.PENDING_CUSTOMER, False))


@override_settings(BACKGROUND_JOBS_ENABLED=True)
class RelayTests(TestCase):
    FORM = "Website Contact Form <forms@relay.example>"
    TEXT = "Name: Pat Requester\nMessage: When does the showcase start on Friday, and is parking free?"

    def setUp(self):
        cache.clear()
        sending_settings(send_acknowledgement=True)

    def relayed(self, *, sender=FORM, reply_to="Pat Requester <pat.requester@example.org>", message_id="<form-1@x>"):
        headers = {"Authentication-Results": DMARC_PASS, **({"Reply-To": reply_to} if reply_to else {})}
        raw = corpus.message(sender=sender, subject="New contact form submission", text=self.TEXT, headers=headers)
        with self.captureOnCommitCallbacks(execute=True):
            return receive(raw.replace(b"<m1@mail.example.org>", message_id.encode()))

    def acknowledgements(self, ticket):
        return list(ticket.messages.filter(kind=Kind.REPLY, automatic=True).values_list("to_addresses", flat=True))

    def under_number(self, ticket, number, reply_to, *, sender=FORM, **headers):
        headers = {"Authentication-Results": DMARC_PASS, **({"Reply-To": reply_to} if reply_to else {}), **headers}
        subject = f"Website contact form: booth size [{ticket.display_number}]"
        raw = corpus.message(sender=sender, subject=subject, text="Send it to me instead.", headers=headers)
        return receive(raw.replace(b"<m1@mail.example.org>", f"<numbered-{number}@x>".encode()))

    def test_a_submission_for_someone_new_under_a_form_tickets_number_opens_their_own(self):
        pat = self.relayed()
        zed = self.relayed(sender="Zed Alpha <wordpress@site.example>", reply_to="Zed <zed@x.org>", message_id="<z@x>")
        steve = self.under_number(pat, 1, "Steve Stranger <steve@example.net>")
        spam = self.under_number(pat, 2, "Mal Payne <mal@example.net>", **{"X-MS-Exchange-Organization-SCL": "6"})
        named = self.under_number(zed, 3, "Steve S <steve@example.net>", sender="Steve S <wordpress@site.example>")

        self.assertEqual(len({pat.pk, zed.pk, steve.pk, spam.pk, named.pk}), 5)
        self.assertEqual((steve.requester_email, spam.status), ("steve@example.net", Status.SPAM))
        self.assertEqual(steve.events.get(kind=TicketEvent.Kind.MENTION).data, {"number": pat.number})
        self.assertEqual(self.under_number(pat, 4, "Pat Requester <pat.requester@example.org>").pk, pat.pk)
        pat.refresh_from_db()
        self.assertNotIn("steve@example.net", pat.participants)

    def test_a_nameless_submission_under_the_number_is_no_requesters_answer(self):
        pat, agent = self.relayed(), helpdesk_staff()
        self.relayed(reply_to="Quinn Other <quinn@example.org>", message_id="<form-5@x>")  # it writes for others
        for number, reply_to in ((5, ""), (6, "pat.requester@example.org")):
            pat.refresh_from_db()
            tickets.update_ticket(pat, actor=agent, status=Status.PENDING_CUSTOMER)
            self.assertEqual(self.under_number(pat, number, reply_to).pk, pat.pk)

        reasons = [event.data.get("reason") for event in pat.events.filter(kind=TicketEvent.Kind.STATUS)]
        self.assertEqual([reason for reason in reasons if reason], ["a participant wrote", "the requester replied"])
        self.assertNotIn("forms@relay.example", outbound.cc_suggestions(pat))

    def test_the_relayed_person_is_the_requester_and_gets_the_staff_reply_but_no_acknowledgement(self):
        ticket = self.relayed()

        self.assertEqual(
            (ticket.requester_name, ticket.requester_email), ("Pat Requester", "pat.requester@example.org")
        )
        self.assertIn("forms@relay.example", ticket.participants)
        self.assertEqual(self.acknowledgements(ticket), [])
        with self.captureOnCommitCallbacks(execute=True):
            reply = outbound.queue_reply(ticket, actor=helpdesk_staff(), body="It starts at 10, and parking is free.")
        self.assertEqual(reply.to_addresses, ["pat.requester@example.org"])

    def test_without_a_reply_to_the_sender_is_the_requester_and_is_acknowledged(self):
        ticket = self.relayed(sender="Pat Doe <pat@example.org>", reply_to="")

        self.assertEqual(ticket.requester_email, "pat@example.org")
        self.assertEqual(self.acknowledgements(ticket), [["pat@example.org"]])

    def test_a_reply_to_naming_several_people_takes_the_first_and_keeps_them_all(self):
        several = self.relayed(reply_to="pat@example.org, Kim Lee <kim@example.org>", message_id="<form-2@x>")
        same = self.relayed(sender="Pat Doe <pat@example.org>", reply_to="PAT@example.org", message_id="<form-3@x>")

        self.assertEqual((several.requester_email, same.requester_email), ("pat@example.org", "pat@example.org"))
        self.assertTrue({"forms@relay.example", "pat@example.org", "kim@example.org"} <= set(several.participants))
        self.assertEqual(self.acknowledgements(several), [])  # the form never gets one, nor an unproven Reply-To

    def test_a_form_relayed_from_a_no_reply_address_is_a_persons_message_never_answered_automatically(self):
        ticket = self.relayed(sender="noreply@relay.example", reply_to="Robin Person <robin.person@example.org>")
        bulk = self.relayed(sender="noreply@relay.example", reply_to="", message_id="<form-4@x>")

        message = ticket.messages.get()
        self.assertEqual((ticket.automated, ticket.status, ticket.classification), (False, Status.NEW, "human"))
        self.assertEqual(ticket.requester_email, "robin.person@example.org")
        self.assertIn("noreply_relay", message.signals)
        self.assertIn(NO_AUTO_RESPONSE, message.signals)
        self.assertEqual(self.acknowledgements(ticket), [])
        self.assertEqual((bulk.automated, bulk.classification), (True, "bulk"))
