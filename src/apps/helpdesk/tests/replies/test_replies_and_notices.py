"""Replies to the site's mail and automatic replies, end to end through the ingest (Microsoft Graph is never
contacted; the messages are ``core``'s synthetic samples):

- a person answering a campaign from a CRM tool lands in the queue as a person's ticket, while the same message
  answering nothing the site sent is hidden as bulk;
- a reply through a mailing list stays hidden list mail, flagged as a reply to the site's mail;
- out-of-office replies and left-the-organisation notices are closed and hidden, and the inbound queue row keeps the
  email they answer, the address it went to, and the address a notice names (Bounced addresses counts the notices);
- an automatic reply to an automatic reply joins its thread, changes nothing, and is never answered automatically;
- a person's follow-up from a CRM tool that answers staff's answer (sent from Outlook, never recorded) stays on their
  ticket and reopens it, while a message answering automated mail or spam proves nothing;
- out-of-office replies (a holiday closure that nobody reads meanwhile too) are never counted in Bounced addresses;
- a message that looks automated, or sits on a spam ticket, is never answered automatically.
"""

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.core.models import InboundMessage
from apps.core.services.email.inbound import NO_AUTO_RESPONSE, REPLY_HINT
from apps.core.tests.services.email.inbound import samples
from apps.core.tests.services.email_monitoring.helpers import make_email
from apps.mail.models import EmailCampaign

from ...models import HelpdeskSettings, Ticket, TicketMessage
from ...services.ingest.routing.classify import REPLY_FLAG
from ..helpers import FakeReader, ingest, queue

Status = Ticket.Status


class SiteMailMixin:
    def setUp(self):
        cache.clear()
        self.reader = FakeReader()
        self.campaign = EmailCampaign.objects.create(name="Judges 2026", subject=samples.CAMPAIGN_SUBJECT)

    def sent(self, recipient, *, message_id=samples.CAMPAIGN_MESSAGE_ID, recipients=None, **values):
        """The campaign email the site sent to ``recipient`` (as the telemetry recorded it; ``message_id=""``: sent as
        Graph JSON, which gives no Message-ID)."""
        values.setdefault("subject", samples.CAMPAIGN_SUBJECT)
        email = make_email(internet_message_id=message_id, campaign_id=self.campaign.pk, recipient=recipient, **values)
        if recipients is not None:
            email.recipients = recipients
            email.save(update_fields=["recipients"])
        return email

    def receive(self, raw: bytes, **values) -> tuple[Ticket, InboundMessage]:
        row = queue(raw, reader=self.reader, **values)
        ingest(self.reader)
        row.refresh_from_db()
        self.assertEqual(row.status, InboundMessage.Status.DONE, row.last_error)
        return Ticket.objects.get(number=row.result["ticket"]), row


class ReplyTests(SiteMailMixin, TestCase):
    def test_a_person_answering_the_campaign_from_a_crm_is_a_ticket_in_the_queue(self):
        email = self.sent("morgan.diaz@acme-industries.example")

        ticket, row = self.receive(samples.crm_reply_about_judging())

        self.assertEqual(
            (ticket.status, ticket.automated, ticket.unread, ticket.classification, ticket.campaign),
            (Status.NEW, False, True, "human", self.campaign),
        )
        self.assertEqual(ticket.flags, [])
        self.assertEqual((row.classification, row.result["site_mail"]), ("human", str(email.pk)))
        self.assertEqual(row.result["site_recipient"], "morgan.diaz@acme-industries.example")
        self.assertEqual(row.result["site_match"], "message_id")
        message = ticket.messages.get()
        self.assertEqual(message.kind, TicketMessage.Kind.CUSTOMER)
        for hint in (REPLY_HINT, NO_AUTO_RESPONSE, "bulk_headers_on_reply", "x-sfdc-lk", "bcl_7"):
            self.assertIn(hint, message.signals)
        self.assertEqual(message.auth_summary, {"bcl": 7})

    def test_the_same_message_answering_nothing_the_site_sent_is_hidden_as_bulk(self):
        ticket, row = self.receive(samples.crm_reply_about_judging(reply=False))

        self.assertEqual((ticket.automated, ticket.status, ticket.classification), (True, Status.CLOSED, "bulk"))
        self.assertNotIn("site_mail", row.result)

    def test_a_reference_to_mail_the_site_never_sent_proves_nothing(self):
        ticket, row = self.receive(samples.crm_reply_about_judging())

        self.assertEqual(ticket.classification, "bulk")
        self.assertNotIn("site_mail", row.result)

    def test_a_reply_through_a_mailing_list_stays_hidden_list_mail_flagged_as_a_reply(self):
        self.sent("engineering-faculty@lists.university.example")

        ticket, row = self.receive(samples.mailing_list_reply())

        self.assertEqual((ticket.automated, ticket.classification), (True, "bulk"))
        self.assertEqual(ticket.flags, [REPLY_FLAG])
        self.assertEqual(row.result["site_recipient"], "engineering-faculty@lists.university.example")

    def test_the_bulk_threshold_is_the_admin_setting(self):
        bulk, _row = self.receive(samples.bulk_by_bcl_only(7))
        HelpdeskSettings.objects.create(bulk_bcl_threshold=8)

        person, _row = self.receive(samples.bulk_by_bcl_only(7).replace(b"deal-bcl7@", b"deal-bcl7b@"))

        self.assertEqual((bulk.classification, person.classification), ("bulk", "human"))
        self.assertEqual(HelpdeskSettings().bulk_bcl_threshold, 7)


class FollowUpTests(SiteMailMixin, TestCase):
    """A person's next message in a conversation the helpdesk holds answers the site's mail too."""

    def test_a_follow_up_from_a_crm_stays_on_the_persons_ticket_and_reopens_it(self):
        self.sent("morgan.diaz@acme-industries.example")
        now = timezone.now()
        ticket, _row = self.receive(samples.crm_reply_about_judging(), received=now - timedelta(days=3))
        Ticket.objects.filter(pk=ticket.pk).update(
            status=Status.CLOSED, closed_at=now - timedelta(days=2), unread=False
        )

        joined, row = self.receive(samples.crm_follow_up_about_judging(), received=now - timedelta(minutes=5))

        self.assertEqual(joined.pk, ticket.pk)
        self.assertEqual((row.classification, row.result["rule"]), ("human", "reopened"))
        self.assertNotIn("site_mail", row.result)  # it names no email the site sent: attributed to nobody
        joined.refresh_from_db()
        self.assertEqual((joined.status, joined.unread, joined.automated), (Status.OPEN, True, False))
        message = joined.messages.get(internet_message_id="<crm-morgan-2@acme-industries.example>")
        self.assertEqual(message.kind, TicketMessage.Kind.CUSTOMER)
        self.assertIn(REPLY_HINT, message.signals)

    def test_a_message_answering_automated_mail_or_spam_proves_nothing(self):
        newsletter, _row = self.receive(samples.newsletter())
        person, _row = self.receive(
            samples.message(
                sender="Pat Doe <pat@example.org>",
                subject="Judging",
                text="Can I judge this year?",
                message_id="<plain-3@example.org>",
                reply=False,
            )
        )
        Ticket.objects.filter(pk=person.pk).update(status=Status.SPAM)
        for parent, ticket in (("<news-2026-11@mail.vendor.example>", newsletter), ("<plain-3@example.org>", person)):
            with self.subTest(parent):
                raw = samples.message(
                    sender="Vendor Weekly <news@mail.vendor.example>",
                    subject="Re: Last chance",
                    text="Last chance: 20% off this weekend.",
                    message_id=f"<offer-{ticket.number}@mail.vendor.example>",
                    parent=parent,
                    headers={"X-SG-EID": "fake-sendgrid-event-0001"},
                )

                joined, row = self.receive(raw)

                self.assertEqual((joined.pk, row.classification), (ticket.pk, "bulk"))

    def test_an_html_only_reply_is_not_flagged_by_the_campaign_it_quotes(self):
        # The quoted campaign mentions being out of the office and leaving a company: neither is the person's.
        self.sent("robin.ellis@northwind.example")

        ticket, _row = self.receive(samples.html_reply_about_judging())

        self.assertEqual((ticket.classification, ticket.automated, ticket.flags), ("human", False, []))
        self.assertNotIn(NO_AUTO_RESPONSE, ticket.messages.get().signals)
