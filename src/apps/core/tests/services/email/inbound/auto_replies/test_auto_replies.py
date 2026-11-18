"""Automatic replies, on the synthetic samples: out-of-office replies (English and Spanish, with and without the
subject prefix), left-the-organisation notices (naming a contact, a new address, nothing; in Spanish; an Exchange
rule's reply), the quoted original never deciding anything, the address a notice names, and the loop protection: an
automatic reply stays automated whatever it answers, and a message that must not be answered automatically says so.
Pure: no database."""

from django.test import SimpleTestCase

from apps.core.services.email.inbound import REPLY_HINT, classify
from apps.core.services.email.inbound.classification.autoreply import kind_of

from .. import samples
from ..classify.test_classify import OWN, evidence


def verdict_of(raw: bytes, *, replies: bool = True):
    return classify(samples.evidence_of(raw, replies_to_site_mail=replies), own_addresses=OWN)


class OutOfOfficeTests(SimpleTestCase):
    def test_an_exchange_out_of_office_reply_names_no_contact_even_with_an_alternate_one(self):
        verdict = verdict_of(samples.exchange_oof_english())

        self.assertEqual((verdict.classification, verdict.subtype), ("auto_reply", "vacation"))
        self.assertEqual(verdict.signals, ("auto_submitted", "auto_reply_subject"))
        self.assertEqual((verdict.contact, verdict.contact_kind), ("", ""))
        self.assertEqual((verdict.contact_name, verdict.contact_phone), ("", ""))
        self.assertEqual(verdict.hints, (REPLY_HINT,))

    def test_spanish_out_of_office_replies_with_and_without_the_subject_prefix(self):
        for name in ("exchange_oof_spanish", "gmail_vacation_spanish"):
            with self.subTest(name):
                verdict = verdict_of(getattr(samples, name)())
                self.assertEqual((verdict.classification, verdict.subtype), ("auto_reply", "vacation"))

    def test_absence_wording_in_the_supported_languages(self):
        for text in (
            "I am OOO until 11/16.",
            "I'm on parental leave and will be back in January.",
            "Je suis absent du bureau jusqu'au 16 novembre.",
            "Ich bin bis zum 16.11. nicht im Büro.",
            "Estarei fora do escritório até segunda-feira.",
            "Sono fuori ufficio fino a lunedì.",
            "Ik ben met vakantie tot maandag.",
        ):
            with self.subTest(text):
                self.assertEqual(kind_of(text), "vacation")

    def test_an_absence_wins_over_a_colleague_who_left(self):
        # An out-of-office reply is never evidence against an address, even when it mentions someone who left.
        text = "I am out of the office until Monday. Jordan has left the company; please contact riley@contoso.example."
        verdict = classify(
            evidence({"Auto-Submitted": "auto-replied"}, subject="Automatic reply: Hi", text_head=text),
            own_addresses=OWN,
        )

        self.assertEqual((verdict.classification, verdict.subtype, verdict.contact), ("auto_reply", "vacation", ""))

    def test_returning_a_message_is_not_an_absence(self):
        text = "Jordan Park no longer works at Contoso. We will return to you within two business days."

        self.assertEqual(kind_of(text), "left_org")

    def test_auto_generated_mail_without_reply_or_notice_wording_is_system_mail(self):
        verdict = classify(
            evidence({"Auto-Submitted": "auto-generated"}, subject="Your weekly report", text_head="See attached."),
            own_addresses=OWN,
        )

        self.assertEqual((verdict.classification, verdict.subtype), ("system", "auto_generated"))


class LeftOrganisationTests(SimpleTestCase):
    def test_a_departure_notice_names_a_phone_without_an_email(self):
        verdict = classify(
            evidence(
                {"Auto-Submitted": "auto-replied"},
                subject="Automatic reply: Hello",
                text_head="Jordan Park no longer works here. Please call Riley Chen at (209) 555-0123.",
            ),
            own_addresses=OWN,
        )

        self.assertEqual(
            (verdict.classification, verdict.contact_name, verdict.contact_phone),
            ("left_org", "Riley Chen", "+12095550123"),
        )

    def test_no_longer_with_the_company_naming_who_to_contact_instead(self):
        verdict = verdict_of(samples.left_with_contact())

        self.assertEqual((verdict.classification, verdict.subtype), ("left_org", "left_org"))
        self.assertEqual((verdict.contact, verdict.contact_kind), ("riley.chen@contoso.example", "contact"))
        self.assertEqual((verdict.contact_name, verdict.contact_phone), ("Riley Chen", ""))
        self.assertTrue(verdict.automated)

    def test_a_notice_giving_the_persons_new_address(self):
        verdict = verdict_of(samples.left_with_new_address())

        self.assertEqual(
            (verdict.classification, verdict.contact, verdict.contact_kind),
            ("left_org", "jordan.park@newco.example", "new_address"),
        )

    def test_a_notice_without_a_replacement_contact(self):
        verdict = verdict_of(samples.left_without_contact())

        self.assertEqual((verdict.classification, verdict.contact, verdict.contact_kind), ("left_org", "", ""))

    def test_a_spanish_notice(self):
        verdict = verdict_of(samples.left_spanish())

        self.assertEqual(
            (verdict.classification, verdict.contact, verdict.contact_kind),
            ("left_org", "contacto@constructora.example", "contact"),
        )

    def test_an_exchange_rule_reply_is_a_notice_only_with_a_notices_wording(self):
        notice = verdict_of(samples.left_by_exchange_rule(), replies=False)
        redirected = classify(
            evidence({"X-MS-Exchange-Inbox-Rules-Loop": "pat@example.org"}, text_head="Could I judge this year?"),
            own_addresses=OWN,
        )
        away = classify(
            evidence({"X-MS-Exchange-Generated-Message-Source": "Mailbox Rules Agent"}, text_head="I am on leave."),
            own_addresses=OWN,
        )

        self.assertEqual(
            (notice.classification, notice.signals, notice.contact),
            ("left_org", ("x-ms-exchange-inbox-rules-loop",), "partnerships@contoso.example"),
        )
        self.assertEqual(redirected.classification, "human")
        self.assertIn("exchange_rule_generated", redirected.hints)
        self.assertEqual((away.classification, away.subtype), ("auto_reply", "vacation"))

    def test_left_the_organisation_wording_in_the_supported_languages(self):
        for text in (
            "Jordan has retired from the University.",
            "My last day at Contoso was October 31.",
            "This mailbox has been closed.",
            "Ana ya no labora en la empresa.",
            "Este correo ya no está activo.",
            "Luc ne fait plus partie de l'entreprise.",
            "Herr Bauer ist nicht mehr im Unternehmen tätig.",
            "Ela não trabalha mais na empresa.",
            "Non lavora più presso di noi.",
            "Hij is niet meer werkzaam bij ons.",
        ):
            with self.subTest(text):
                self.assertEqual(kind_of(text), "left_org")

    def test_a_mailbox_nobody_reads_is_no_notice_on_its_own(self):
        # Holiday, weekend and shared mailboxes say so too: only a mailbox no longer read means someone left.
        self.assertEqual(kind_of("This mailbox is not monitored."), "other")
        self.assertEqual(kind_of("This mailbox is no longer monitored."), "left_org")
        self.assertEqual(kind_of("This mailbox is not monitored until we return on January 5."), "vacation")
        self.assertEqual(kind_of("Thanks for writing."), "other")

    def test_a_person_writing_that_they_left_stays_a_person_with_a_hint(self):
        verdict = classify(
            evidence(text_head="Hi! I have left Contoso; my new email address is pat@new.example."),
            own_addresses=OWN,
        )

        self.assertEqual((verdict.classification, verdict.contact), ("human", ""))
        self.assertIn("possible_left_org", verdict.hints)

    def test_temporary_support_does_not_turn_a_departure_notice_into_vacation(self):
        text = "Jordan has left. For temporary support, please contact Riley Chen."

        self.assertEqual(kind_of(text), "left_org")


OUT_OF_OFFICE = (
    "I have left for lunch. For assistance contact Riley Chen at riley@contoso.example.",
    "Our office is closed for the Thanksgiving holiday. This inbox is not being monitored; for urgent matters, write "
    "to help@contoso.example.",
    "I'm away for the holidays and this mailbox is not checked.",
    "I have left for the winter break and will answer in January.",
    "I'm away until 20 November. This mailbox is not monitored while I'm away.",
    "I am attending a conference and will respond upon my return. This mailbox is not monitored.",
    "The campus is closed for winter break from December 24 to January 1. Emails sent to this address are not "
    "monitored during the closure.",
    "I am out sick today. This inbox is not monitored.",
    "I am on the road this week; email is not checked regularly.",
    "Our office hours are 9 to 5. We have left the office for the day and will answer tomorrow.",
    "This mailbox is not monitored on weekends.",
    "I'm travelling until the 20th and this account is not monitored.",
    "I'm on a leave of absence; this mailbox is not monitored. My colleague Jordan has left the company.",
    "This is an out-of-office reply: Jordan has left for vacation.",
    "Este buzón no se revisa durante las vacaciones de invierno.",
    "Ich bin auf Dienstreise; dieses Postfach wird nicht gelesen.",
    "Sono in viaggio fino al 20 novembre; questa casella non è più attiva fino al mio rientro.",
)
