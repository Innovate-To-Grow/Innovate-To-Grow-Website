from django.test import TestCase

from apps.core.models import InboundMessage, OutboundEmail
from apps.core.tests.services.email.inbound import samples
from apps.helpdesk.tests.replies.test_replies_and_notices import SiteMailMixin, Status

from ...models import Ticket
from ...services.ingest.routing.classify import same_organisation


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
                "named_contact_name": "Riley Chen",
            },
        )

    def test_a_phone_in_a_left_org_notice_is_saved_for_review(self):
        self.sent("jordan.park@contoso.example")
        raw = samples.message(
            sender="Jordan Park <jordan.park@contoso.example>",
            subject=f"Automatic reply: {samples.CAMPAIGN_SUBJECT}",
            text="Jordan Park no longer works here. Please contact Riley Chen at (209) 555-0123.",
            message_id="<left-jordan-phone@contoso.example>",
            headers={"Auto-Submitted": "auto-replied"},
        )

        _ticket, row = self.receive(raw)

        self.assertEqual(
            (row.classification, row.result["named_contact_name"], row.result["named_contact_phone"]),
            ("left_org", "Riley Chen", "+12095550123"),
        )

    def test_a_notice_from_another_address_is_matched_to_the_address_mailed(self):
        self.sent("j.park@contoso.example")

        _ticket, row = self.receive(samples.left_with_new_address())

        self.assertEqual(row.result["site_recipient"], "j.park@contoso.example")
        self.assertEqual(
            (row.result["named_contact"], row.result["named_contact_kind"]),
            ("jordan.park@newco.example", "new_address"),
        )

    def test_a_notice_from_another_organisation_is_attributed_to_nobody(self):
        # The email was redirected to someone elsewhere, whose mailbox answered: it says nothing about the address mailed.
        self.sent("morgan.diaz@acme-industries.example")

        _ticket, row = self.receive(samples.left_with_contact())

        self.assertEqual(row.classification, "left_org")
        self.assertIn("site_mail", row.result)
        self.assertNotIn("site_recipient", row.result)

    def test_an_organisation_and_its_subdomains_are_one(self):
        self.assertTrue(same_organisation("it@mail.contoso.example", "jordan@contoso.example"))
        self.assertTrue(same_organisation("jordan@contoso.example", "it@mail.contoso.example"))
        self.assertFalse(same_organisation("jordan@contoso.example", "jordan@notcontoso.example"))
        self.assertFalse(same_organisation("", "jordan@contoso.example"))

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
