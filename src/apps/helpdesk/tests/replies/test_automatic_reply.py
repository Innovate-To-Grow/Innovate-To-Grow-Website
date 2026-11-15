from datetime import timedelta

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.core.models import InboundMessage, OutboundEmail
from apps.core.tests.services.inbound import samples
from apps.helpdesk.tests.replies.test_replies_and_notices import SiteMailMixin
from apps.mail.models import BouncedAddress
from apps.mail.tests.services.bounced_addresses.helpers import count_now

from ...models import HelpdeskSettings, Ticket
from ...services.ingest.reading.message import ParsedMessage
from ...services.ingest.routing.replies import site_mail_replied, subject_stages


class AutomaticReplyTests(SiteMailMixin, TestCase):
    def test_only_the_left_org_notice_counts_never_an_out_of_office_reply(self):
        for recipient in ("alex.kim@contoso.example", "casey.nguyen@contoso.example", "jordan.park@contoso.example"):
            self.sent(recipient, message_id="")
        for raw in (samples.exchange_oof_english(), samples.holiday_closure_notice(), samples.left_with_contact()):
            self.receive(raw)

        result = count_now()

        self.assertEqual(result["inbound"], 1)
        counted = BouncedAddress.objects.filter(left_org_count__gt=0)
        self.assertEqual(list(counted.values_list("address", "left_org_count")), [("jordan.park@contoso.example", 1)])
        holiday = InboundMessage.objects.get(internet_message_id="<oof-casey-1@contoso.example>")
        self.assertEqual((holiday.classification, holiday.subtype), ("auto_reply", "vacation"))


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
