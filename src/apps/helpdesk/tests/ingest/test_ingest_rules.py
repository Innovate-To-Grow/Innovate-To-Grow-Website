"""What every inbound message becomes (Hongzhe's decision of 2026-11-11): a person's or an uncertain message opens or
joins a normal ticket; automated mail opens a ticket closed at once and hidden, joins a thread without changing it,
and never reopens anything; the site's own mail keeps no content. Microsoft Graph is never contacted."""

from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.authn.models import ContactEmail, Member
from apps.core.services.email.inbound import LINK_PLACEHOLDER
from apps.core.tests.services.email_monitoring.helpers import make_email
from apps.mail.models import EmailCampaign

from ...models import Ticket, TicketEvent, TicketMessage
from .. import corpus
from ..helpers import receive

Status = Ticket.Status
Kind = TicketEvent.Kind
AUTOMATED_SAMPLES = {
    "auto_reply": corpus.out_of_office,
    "left_org": corpus.left_organisation,
    "bounce": corpus.bounce_report,
    "receipt": corpus.read_receipt,
    "system": corpus.calendar_reply,
    "bulk": corpus.list_mail,
    "spam": corpus.spam,
    "own": corpus.own_message,
}


def event_kinds(ticket) -> list[str]:
    return list(ticket.events.order_by("created_at").values_list("kind", flat=True))


class PersonTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_a_persons_message_opens_a_visible_unread_ticket(self):
        ticket = receive(corpus.message(cc="Kim <kim@example.org>, Site <i2g@ucmerced.edu>"))

        self.assertGreaterEqual(ticket.number, 1001)
        self.assertEqual(ticket.display_number, f"I2G-#{ticket.number}")
        self.assertEqual(
            (ticket.status, ticket.priority, ticket.automated, ticket.unread, ticket.classification),
            (Status.NEW, Ticket.Priority.NORMAL, False, True, "human"),
        )
        self.assertEqual((ticket.requester_email, ticket.requester_name), ("pat@example.org", "Pat Doe"))
        self.assertEqual(ticket.participants, ["pat@example.org", "kim@example.org"])
        self.assertEqual(ticket.subject, "Question about the showcase")
        self.assertIsNone(ticket.closed_at)
        self.assertFalse(ticket.backfilled)
        self.assertEqual(event_kinds(ticket), [Kind.CREATED])
        message = ticket.messages.get()
        self.assertEqual((message.kind, message.scam_level), (TicketMessage.Kind.CUSTOMER, "low"))
        self.assertEqual(message.occurred_at, ticket.first_message_at)

    def test_the_requester_is_linked_to_the_member_who_owns_the_address(self):
        member = Member.objects.create_user(password="x", first_name="Pat", last_name="Doe")
        ContactEmail.objects.create(
            member=member, email_address="Pat@Example.org", email_type="secondary", verified=True
        )

        self.assertEqual(receive(corpus.message()).requester_member, member)

    def test_a_reply_to_a_campaign_is_a_new_ticket_linked_to_the_campaign(self):
        campaign = EmailCampaign.objects.create(name="Blast", subject="Innovate to Grow 2026")
        make_email(internet_message_id="<blast-1@ucmerced.edu>", campaign_id=campaign.pk)

        ticket = receive(corpus.message(in_reply_to="<blast-1@ucmerced.edu>", subject="Re: Innovate to Grow 2026"))

        self.assertEqual(ticket.campaign, campaign)
        self.assertEqual(ticket.status, Status.NEW)

    def test_mail_imported_long_after_it_arrived_is_backfilled(self):
        old = receive(corpus.message(), received=timezone.now() - timedelta(days=3))

        self.assertTrue(old.backfilled)

    def test_a_high_scam_score_makes_unauthenticated_mail_spam_and_a_medium_one_suspicious(self):
        # corpus.message carries no Authentication-Results; with a DMARC or compauth pass a high score on the words
        # alone gives a suspicious person's ticket instead (tests/service/intake/test_scam_verdict.py).
        findings = "apps.helpdesk.services.ingest.routing.scam.findings"
        with patch(findings, return_value=([(7, "Scored high")], [])):
            spam = receive(corpus.message(message_id="<s1@example.org>"))
        with patch(findings, return_value=([(3, "Scored medium")], [])):
            suspicious = receive(corpus.message(message_id="<s2@example.org>", sender="other@example.org"))

        self.assertEqual((spam.status, spam.automated, spam.classification), (Status.SPAM, True, "spam"))
        self.assertEqual(
            (suspicious.status, suspicious.automated, suspicious.flags), (Status.NEW, False, ["suspicious"])
        )

    def test_a_forged_site_address_is_a_suspicious_ticket(self):
        ticket = receive(corpus.own_message(internal=False))

        self.assertEqual((ticket.automated, ticket.classification), (False, "human"))
        self.assertIn("suspicious", ticket.flags)

    def test_sign_in_links_are_scrubbed_everywhere_they_are_stored(self):
        raw = corpus.message(
            subject=f"Re: link {corpus.LOGIN_LINK}",
            text=f"My link {corpus.LOGIN_LINK} and {corpus.UNSUBSCRIBE_LINK} fail",
            html=f'<p><a href="{corpus.IMPERSONATE_LINK}">link</a></p>',
        )

        ticket = receive(raw)
        forwarded = receive(corpus.forwarded())

        message = ticket.messages.get()
        stored = " ".join((ticket.subject, message.subject, message.body_text, message.body_html))
        self.assertNotIn("token=", stored)
        self.assertNotIn("unsubscribe/", stored)
        self.assertEqual(stored.count(LINK_PLACEHOLDER), 5)  # two subjects, two links in the text, one in the HTML
        (attached,) = forwarded.messages.get().attached_messages
        self.assertEqual(attached["text"].strip(), f"Sign in here: {LINK_PLACEHOLDER}")


class _AutomatedMailCase(TestCase):
    def setUp(self):
        cache.clear()


class AutomatedMailTests(_AutomatedMailCase):
    def test_every_automated_class_opens_a_closed_hidden_low_priority_ticket(self):
        for classification, build in AUTOMATED_SAMPLES.items():
            with self.subTest(classification):
                ticket = receive(build())
                self.assertEqual(ticket.classification, classification)
                self.assertTrue(ticket.automated)
                self.assertEqual(ticket.status, Status.SPAM if classification == "spam" else Status.CLOSED)
                self.assertEqual((ticket.priority, ticket.unread), (Ticket.Priority.LOW, False))
                self.assertEqual(ticket.closed_at, ticket.first_message_at)
                self.assertEqual(ticket.messages.get().kind, TicketMessage.Kind.AUTOMATED)
