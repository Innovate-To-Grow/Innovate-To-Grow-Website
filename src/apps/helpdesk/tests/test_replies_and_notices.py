"""Replies to the site's mail and automatic replies, end to end through the ingest (Microsoft Graph is never
contacted; the messages are ``core``'s synthetic samples):

- a person answering a campaign from a CRM tool lands in the queue as a person's ticket, while the same message
  answering nothing the site sent is hidden as bulk;
- a reply through a mailing list stays hidden list mail, flagged as a reply to the site's mail;
- out-of-office replies and left-the-organisation notices are closed and hidden, and the inbound queue row keeps the
  email they answer, the address it went to, and the address a notice names (Bounced addresses counts the notices);
- an automatic reply to an automatic reply joins its thread, changes nothing, and is never answered automatically.
"""

from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.core.models import InboundMessage, OutboundEmail
from apps.core.services.email.inbound import NO_AUTO_RESPONSE, REPLY_HINT
from apps.core.tests.services.email_monitoring.helpers import make_email
from apps.core.tests.services.inbound import samples
from apps.mail.models import EmailCampaign

from ..models import HelpdeskSettings, Ticket, TicketEvent, TicketMessage
from ..services import shadow
from ..services.ingest.classify import REPLY_FLAG
from ..services.ingest.parse import ParsedMessage
from ..services.ingest.replies import site_mail_replied, subject_stages
from .helpers import FakeReader, ingest, queue

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

    def receive(self, raw: bytes) -> tuple[Ticket, InboundMessage]:
        row = queue(raw, reader=self.reader)
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


class AutomaticReplyTests(SiteMailMixin, TestCase):
    def test_out_of_office_replies_in_english_and_spanish_are_hidden_and_name_nothing(self):
        for raw, recipient in (
            (samples.exchange_oof_english(), "alex.kim@contoso.example"),
            (samples.exchange_oof_spanish(), "maria.lopez@empresa.example"),
        ):
            with self.subTest(recipient):
                for model in (InboundMessage, Ticket, OutboundEmail):
                    model.objects.all().delete()
                self.sent(recipient)

                ticket, row = self.receive(raw)

                self.assertEqual(
                    (ticket.automated, ticket.status, ticket.classification), (True, Status.CLOSED, "auto_reply")
                )
                self.assertEqual((row.classification, row.subtype), ("auto_reply", "vacation"))
                self.assertEqual(row.result["site_recipient"], recipient)
                self.assertNotIn("named_contact", row.result)
                self.assertEqual(ticket.flags, [])

    def test_a_left_org_notice_keeps_the_address_mailed_and_the_contact_it_names(self):
        email = self.sent("jordan.park@contoso.example")

        ticket, row = self.receive(samples.left_with_contact())

        self.assertEqual((ticket.automated, ticket.status, ticket.classification), (True, Status.CLOSED, "left_org"))
        self.assertEqual(
            row.result,
            {
                "ticket": ticket.number,
                "created": True,
                "rule": "new",
                "site_mail": str(email.pk),
                "site_match": "message_id",
                "site_recipient": "jordan.park@contoso.example",
                "named_contact": "riley.chen@contoso.example",
                "named_contact_kind": "contact",
            },
        )

    def test_a_notice_from_another_address_is_matched_to_the_address_mailed(self):
        self.sent("j.park@contoso.example")

        _ticket, row = self.receive(samples.left_with_new_address())

        self.assertEqual(row.result["site_recipient"], "j.park@contoso.example")
        self.assertEqual(
            (row.result["named_contact"], row.result["named_contact_kind"]),
            ("jordan.park@newco.example", "new_address"),
        )

    def test_an_email_to_several_people_matches_the_sender_or_nobody(self):
        self.sent("a@contoso.example", recipients=["a@contoso.example", "Jordan.Park@contoso.example"])
        _ticket, matched = self.receive(samples.left_with_contact())
        for model in (InboundMessage, Ticket, OutboundEmail):
            model.objects.all().delete()
        self.sent("a@contoso.example", recipients=["a@contoso.example", "b@contoso.example"])

        _ticket, unmatched = self.receive(samples.left_with_contact())

        self.assertEqual(matched.result["site_recipient"], "jordan.park@contoso.example")
        self.assertIn("site_mail", unmatched.result)
        self.assertNotIn("site_recipient", unmatched.result)

    def test_a_notice_naming_the_address_mailed_names_no_contact(self):
        self.sent("j.park@contoso.example")
        raw = samples.message(
            sender="Jordan Park <jordan.park@contoso.example>",
            subject=f"Automatic reply: {samples.CAMPAIGN_SUBJECT}",
            text="Jordan Park no longer works at Contoso; j.park@contoso.example is closed.",
            message_id="<left-jordan-3@contoso.example>",
            headers={"Auto-Submitted": "auto-replied"},
        )

        _ticket, row = self.receive(raw)

        self.assertEqual(row.classification, "left_org")
        self.assertNotIn("named_contact", row.result)

    def test_a_notice_answering_nothing_the_site_sent_records_no_address(self):
        _ticket, row = self.receive(samples.left_without_contact())

        self.assertEqual(row.classification, "left_org")
        self.assertNotIn("site_recipient", row.result)

    def test_a_second_copy_keeps_no_facts(self):
        self.sent("taylor.brooks@fabrikam.example")
        raw = samples.left_without_contact().replace(b"Message-ID: <left-taylor-1@fabrikam.example>\r\n", b"")

        first, _row = self.receive(raw)
        again, row = self.receive(raw)

        self.assertEqual(first.pk, again.pk)
        self.assertEqual(row.result, {"ticket": first.number, "created": False, "rule": "duplicate", "duplicate": True})


class InferredReplyTests(SiteMailMixin, TestCase):
    """Campaign mail with a sign-in link is sent as Graph JSON: the site never learns its Message-ID."""

    def crm_reply(self, subject=f"RE: [EXTERNAL] {samples.CAMPAIGN_SUBJECT}") -> bytes:
        return samples.crm_reply_about_judging().replace(
            f"Subject: RE: {samples.CAMPAIGN_SUBJECT}".encode(), f"Subject: {subject}".encode()
        )

    def test_a_reply_from_the_address_mailed_with_the_same_subject_is_a_reply_to_our_mail(self):
        email = self.sent("morgan.diaz@acme-industries.example", message_id="")

        ticket, row = self.receive(self.crm_reply())

        self.assertEqual((ticket.classification, ticket.automated, ticket.campaign), ("human", False, self.campaign))
        self.assertEqual(
            (row.result["site_mail"], row.result["site_match"], row.result["site_recipient"]),
            (str(email.pk), "recipient_subject", "morgan.diaz@acme-industries.example"),
        )

    def test_an_automatic_reply_and_a_notice_to_such_mail_are_matched_too(self):
        self.sent("alex.kim@contoso.example", message_id="")
        self.sent("jordan.park@contoso.example", message_id="")

        _ticket, oof = self.receive(samples.exchange_oof_english())
        _ticket, notice = self.receive(samples.left_with_contact())

        self.assertEqual((oof.classification, oof.result["site_match"]), ("auto_reply", "recipient_subject"))
        self.assertEqual(notice.result["site_recipient"], "jordan.park@contoso.example")

    def test_no_inference_without_the_same_sender_subject_window_or_an_unknown_message_id(self):
        cases = (
            ("someone.else@acme-industries.example", {"message_id": ""}, self.crm_reply()),
            ("morgan.diaz@acme-industries.example", {"message_id": ""}, self.crm_reply("RE: Another subject")),
            (
                "morgan.diaz@acme-industries.example",
                {"message_id": "", "last_attempt_at": timezone.now() - timedelta(days=31)},
                self.crm_reply(),
            ),
            ("morgan.diaz@acme-industries.example", {"message_id": "<known@outlook.example>"}, self.crm_reply()),
            ("morgan.diaz@acme-industries.example", {"message_id": "", "status": "failed"}, self.crm_reply()),
        )
        for recipient, values, raw in cases:
            with self.subTest(recipient=recipient, values=values):
                for model in (InboundMessage, Ticket, OutboundEmail):
                    model.objects.all().delete()
                self.sent(recipient, **values)

                ticket, row = self.receive(raw)

                self.assertEqual(ticket.classification, "bulk")
                self.assertNotIn("site_mail", row.result)

    def test_a_message_that_is_no_reply_is_never_inferred(self):
        self.sent("morgan.diaz@acme-industries.example", message_id="")

        ticket, row = self.receive(samples.crm_reply_about_judging(reply=False))

        self.assertEqual(ticket.classification, "bulk")
        self.assertNotIn("site_mail", row.result)

    def test_a_reply_without_a_sender_or_a_subject_is_never_inferred(self):
        self.sent("morgan.diaz@acme-industries.example", message_id="", subject="")
        window = timedelta(days=30)
        for values in (
            {"from_address": "", "subject": f"RE: {samples.CAMPAIGN_SUBJECT}"},
            {"from_address": "morgan.diaz@acme-industries.example", "subject": ""},
        ):
            with self.subTest(values):
                parsed = ParsedMessage(headers={}, in_reply_to="<unknown@acme-industries.example>", **values)
                self.assertIsNone(site_mail_replied(parsed, received_at=timezone.now(), window=window))

    def test_the_window_is_the_admin_setting(self):
        HelpdeskSettings.objects.create(reply_match_window_days=40)
        self.sent(
            "morgan.diaz@acme-industries.example", message_id="", last_attempt_at=timezone.now() - timedelta(days=35)
        )

        ticket, _row = self.receive(self.crm_reply())

        self.assertEqual(ticket.classification, "human")


class SubjectStageTests(SimpleTestCase):
    def test_every_leading_tag_comes_off_one_at_a_time(self):
        self.assertEqual(
            subject_stages("RE: [EXTERNAL] Automatic reply: AW: *EXT* [I2G] Judges"),
            [
                "RE: [EXTERNAL] Automatic reply: AW: *EXT* [I2G] Judges",
                "[EXTERNAL] Automatic reply: AW: *EXT* [I2G] Judges",
                "Automatic reply: AW: *EXT* [I2G] Judges",
                "AW: *EXT* [I2G] Judges",
                "*EXT* [I2G] Judges",
                "[I2G] Judges",
                "Judges",
            ],
        )

    def test_a_subject_that_is_only_a_tag_or_has_none_stays(self):
        self.assertEqual(subject_stages("[EXTERNAL]"), ["[EXTERNAL]"])
        self.assertEqual(subject_stages("Judges wanted"), ["Judges wanted"])
        self.assertEqual(subject_stages(""), [""])
        self.assertEqual(len(subject_stages("RE: " * 50 + "x")), 11)


class LoopTests(SiteMailMixin, TestCase):
    def test_an_automatic_reply_to_an_automatic_reply_joins_its_thread_and_changes_nothing(self):
        self.sent("alex.kim@contoso.example")
        first, _row = self.receive(samples.exchange_oof_english())
        before = Ticket.objects.get(pk=first.pk)

        joined, row = self.receive(samples.auto_reply_to_auto_reply())

        self.assertEqual(joined.pk, first.pk)
        self.assertEqual((row.classification, row.result["rule"]), ("auto_reply", "references"))
        joined.refresh_from_db()
        self.assertEqual(
            (joined.status, joined.unread, joined.last_activity_at, joined.closed_at),
            (Status.CLOSED, False, before.last_activity_at, before.closed_at),
        )
        self.assertEqual(Ticket.objects.count(), 1)
        self.assertTrue(joined.events.filter(kind=TicketEvent.Kind.AUTOMATED_MESSAGE).exists())

    def test_no_automatic_answer_is_ever_allowed_for_automated_mail(self):
        self.sent("alex.kim@contoso.example")
        self.receive(samples.exchange_oof_english())
        self.receive(samples.auto_reply_to_auto_reply())
        settings = HelpdeskSettings.objects.create(shadow_mode=False)

        with patch.object(shadow, "SENDING_IMPLEMENTED", True):
            self.assertTrue(shadow.sending_allowed(settings))
            for message in TicketMessage.objects.all():
                self.assertFalse(shadow.automatic_reply_allowed(message, settings))

    def test_a_persons_message_may_be_answered_only_once_sending_exists_and_rfc_3834_allows(self):
        self.sent("morgan.diaz@acme-industries.example")
        crm, _row = self.receive(samples.crm_reply_about_judging())
        plain, _row = self.receive(
            samples.message(
                sender="Pat Doe <pat@example.org>",
                subject="Judging",
                text="Can I judge this year?",
                message_id="<plain-1@example.org>",
                reply=False,
            )
        )
        settings = HelpdeskSettings.objects.create(shadow_mode=False)
        crm_message, plain_message = crm.messages.get(), plain.messages.get()

        self.assertFalse(shadow.automatic_reply_allowed(plain_message, settings))  # this release sends nothing
        with patch.object(shadow, "SENDING_IMPLEMENTED", True):
            self.assertTrue(shadow.automatic_reply_allowed(plain_message, settings))
            self.assertFalse(shadow.automatic_reply_allowed(crm_message, settings))
