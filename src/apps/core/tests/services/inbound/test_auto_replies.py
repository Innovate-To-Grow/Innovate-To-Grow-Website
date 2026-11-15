"""Automatic replies, on the synthetic samples: out-of-office replies (English and Spanish, with and without the
subject prefix), left-the-organisation notices (naming a contact, a new address, nothing; in Spanish; an Exchange
rule's reply), the quoted original never deciding anything, the address a notice names, and the loop protection: an
automatic reply stays automated whatever it answers, and a message that must not be answered automatically says so.
Pure: no database."""

from django.test import SimpleTestCase

from apps.core.services.email.inbound import NO_AUTO_RESPONSE, REPLY_HINT, classify
from apps.core.services.email.inbound.autoreply import kind_of, named_contact, own_subject, own_text, response_allowed
from apps.core.services.email.inbound.rules import ESP_HEADERS

from . import samples
from .test_classify import OWN, evidence


def verdict_of(raw: bytes, *, replies: bool = True):
    return classify(samples.evidence_of(raw, replies_to_site_mail=replies), own_addresses=OWN)


class OutOfOfficeTests(SimpleTestCase):
    def test_an_exchange_out_of_office_reply_names_no_contact_even_with_an_alternate_one(self):
        verdict = verdict_of(samples.exchange_oof_english())

        self.assertEqual((verdict.classification, verdict.subtype), ("auto_reply", "vacation"))
        self.assertEqual(verdict.signals, ("auto_submitted", "auto_reply_subject"))
        self.assertEqual((verdict.contact, verdict.contact_kind), ("", ""))
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
    def test_no_longer_with_the_company_naming_who_to_contact_instead(self):
        verdict = verdict_of(samples.left_with_contact())

        self.assertEqual((verdict.classification, verdict.subtype), ("left_org", "left_org"))
        self.assertEqual((verdict.contact, verdict.contact_kind), ("riley.chen@contoso.example", "contact"))
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


OUT_OF_OFFICE = (
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


class OutOfOfficeIsNeverEvidenceTests(SimpleTestCase):
    """Only left-the-organisation notices count against an address: an out-of-office reply is never one, whatever
    else it says (a holiday closure, a mailbox nobody reads meanwhile, a colleague who left)."""

    def test_out_of_office_replies_are_vacation_replies(self):
        for text in OUT_OF_OFFICE:
            with self.subTest(text):
                verdict = classify(
                    evidence(
                        {"Auto-Submitted": "auto-replied"},
                        subject=f"Automatic reply: {samples.CAMPAIGN_SUBJECT}",
                        text_head=text,
                    ),
                    own_addresses=OWN,
                )
                self.assertEqual(
                    (verdict.classification, verdict.subtype, verdict.contact), ("auto_reply", "vacation", "")
                )

    def test_a_holiday_closure_that_nobody_reads_meanwhile_is_a_vacation_reply(self):
        verdict = verdict_of(samples.holiday_closure_notice())

        self.assertEqual((verdict.classification, verdict.subtype), ("auto_reply", "vacation"))

    def test_an_acknowledgement_mentioning_a_voicemail_is_no_notice(self):
        verdict = classify(
            evidence(
                {"Auto-Submitted": "auto-replied"},
                subject="Automatic reply: Hello",
                text_head="If you have left a voicemail, we will return your call within one business day.",
            ),
            own_addresses=OWN,
        )

        self.assertEqual((verdict.classification, verdict.subtype), ("auto_reply", "other"))

    def test_notices_without_an_absence_still_count(self):
        for text in (
            "Jordan has left our organization; for project questions, write to eng@contoso.example during business "
            "hours.",
            "Jordan has left us for a new opportunity. Please contact riley@contoso.example.",
            "My last day at Contoso was Friday, November 6. Please use my new address: jordan@newco.example.",
        ):
            with self.subTest(text):
                verdict = classify(
                    evidence({"Auto-Submitted": "auto-generated"}, subject="Automatic reply: Hi", text_head=text),
                    own_addresses=OWN,
                )
                self.assertEqual(verdict.classification, "left_org")

    def test_the_wider_absence_wording_never_hides_a_persons_message(self):
        # With only Exchange's rule marker, absence wording that a person writes too is no notice.
        verdict = classify(
            evidence(
                {"X-MS-Exchange-Inbox-Rules-Loop": "pat@example.org"},
                text_head="I'm away next week, but please count me in as a judge. I'll be travelling until the 20th.",
            ),
            own_addresses=OWN,
        )

        self.assertEqual(verdict.classification, "human")

    def test_no_break_spaces_do_not_hide_the_wording(self):
        # HTML text is full of them; the phrases are written with plain spaces.
        self.assertEqual(kind_of(own_text("I am out\xa0of\xa0the\xa0office.")), "vacation")
        self.assertEqual(kind_of(own_text("Jordan  has\tleft\xa0the company.")), "left_org")


class QuotedOriginalTests(SimpleTestCase):
    def test_the_quoted_campaign_never_decides(self):
        # The quoted campaign says "out of the office" and "no longer with your company": neither is the answer's.
        verdict = verdict_of(samples.crm_reply_about_judging())

        self.assertNotIn("possible_auto_reply", verdict.hints)
        self.assertNotIn("possible_left_org", verdict.hints)

    def test_every_quote_marker_ends_the_text_a_message_wrote_itself(self):
        for marker in (
            "-----Original Message-----",
            "________________________________",
            "On Tue, Nov 10, 2026 at 9:00 AM Innovate to Grow <i2g@ucmerced.edu> wrote:",
            "El mar, 10 nov 2026 a las 9:00, Innovate to Grow (<i2g@ucmerced.edu>) escribió:",
            "Le mar. 10 nov. 2026 à 09:00, Innovate to Grow <i2g@ucmerced.edu> a écrit :",
            "Am 10.11.2026 um 09:00 schrieb Innovate to Grow <i2g@ucmerced.edu>:",
            "From: Innovate to Grow <i2g@ucmerced.edu>\nSent: Tuesday, November 10, 2026 9:00 AM",
            "De: Innovate to Grow\nEnviado: martes, 10 de noviembre de 2026 9:00",
            "> We are looking for judges.",
        ):
            with self.subTest(marker):
                self.assertEqual(own_text(f"My own words.\n{marker}\nquoted text"), "My own words.\n")

    def test_a_header_block_with_each_label_on_its_own_line_ends_it_too(self):
        # How an HTML-only message's text gives Outlook's header block (French Outlook puts a space before colons).
        for block in (
            "From:\n Innovate to Grow <i2g@ucmerced.edu>\n\n\nSent:\n Tuesday, November 10, 2026",
            "De :\n Innovate to Grow\nEnvoyé :\n mardi 10 novembre 2026",
        ):
            with self.subTest(block):
                self.assertEqual(own_text(f"Count me in!\n{block}\nIf you are out of the office..."), "Count me in!\n")

    def test_a_from_line_without_a_date_line_is_the_messages_own(self):
        text = "From: the judging team\nWe would love to help."

        self.assertEqual(own_text(text), text)

    def test_notice_wording_only_in_the_quote_leaves_an_automatic_reply_unexplained(self):
        text = "Thanks for your note.\n\n" + samples.QUOTED_CAMPAIGN
        verdict = classify(
            evidence({"Auto-Submitted": "auto-replied"}, subject="Automatic reply: Hi", text_head=text),
            own_addresses=OWN,
        )

        self.assertEqual((verdict.classification, verdict.subtype), ("auto_reply", "other"))


class OriginalSubjectTests(SimpleTestCase):
    """A reply's subject is mostly the site's own campaign subject: its words are not the sender's."""

    def test_a_reply_or_an_automatic_reply_subject_has_no_words_of_its_own(self):
        for subject in (
            "Automatic reply: Register until Monday",
            "RE: Register until Monday",
            "[EXTERNAL] RE: Register until Monday",
            "AW[2]: Register until Monday",
            "Respuesta automática: Inscripciones hasta el lunes",
        ):
            with self.subTest(subject):
                self.assertEqual(own_subject(subject), "")
        self.assertEqual(own_subject("Jordan Park has left Contoso"), "Jordan Park has left Contoso")
        self.assertEqual(own_subject("Regarding: judges"), "Regarding: judges")

    def test_the_campaigns_subject_never_decides_what_a_notice_says(self):
        left = classify(
            evidence(
                {"Auto-Submitted": "auto-generated"},
                subject="Automatic reply: Register until Monday",
                text_head="Jordan Park no longer works at Contoso.",
            ),
            own_addresses=OWN,
        )
        away = classify(
            evidence(
                {"Auto-Submitted": "auto-replied"},
                subject="Automatic reply: Our new email address for the showcase",
                text_head="I am out of the office until Monday.",
            ),
            own_addresses=OWN,
        )

        self.assertEqual((left.classification, away.subtype), ("left_org", "vacation"))

    def test_a_notices_own_subject_still_counts(self):
        verdict = classify(
            evidence(
                {"X-MS-Exchange-Inbox-Rules-Loop": "jordan.park@contoso.example"},
                subject="Jordan Park has left Contoso",
                text_head="Please write to partnerships@contoso.example.",
            ),
            own_addresses=OWN,
        )

        self.assertEqual((verdict.classification, verdict.contact), ("left_org", "partnerships@contoso.example"))

    def test_a_persons_reply_is_not_flagged_by_the_campaigns_subject(self):
        verdict = classify(
            evidence(subject="RE: [EXTERNAL] Judges wanted until Friday", text_head="Count me in!"),
            own_addresses=OWN,
        )

        self.assertEqual(verdict.hints, ())


class NamedContactTests(SimpleTestCase):
    def test_the_sender_the_site_and_report_or_no_reply_addresses_are_never_named(self):
        text = (
            "Write to jordan.park@contoso.example, i2g@ucmerced.edu, postmaster@contoso.example or noreply@x.example."
        )

        self.assertEqual(named_contact(text, {"jordan.park@contoso.example", "i2g@ucmerced.edu"}), ("", ""))

    def test_a_new_address_wins_over_an_earlier_contact(self):
        text = "Please contact info@contoso.example. My new e-mail address: jordan@newco.example."

        self.assertEqual(named_contact(text, set()), ("jordan@newco.example", "new_address"))

    def test_the_only_address_without_an_introduction_is_mentioned_and_two_are_too_unclear(self):
        self.assertEqual(
            named_contact("Jordan left. riley@contoso.example", set()), ("riley@contoso.example", "mentioned")
        )
        self.assertEqual(named_contact("See a@x.example and b@y.example", set()), ("", ""))

    def test_an_introduction_in_an_earlier_sentence_does_not_count(self):
        text = "Please contact our office. Records: archive@contoso.example; files@contoso.example"

        self.assertEqual(named_contact(text, set()), ("", ""))

    def test_new_address_wording_in_other_languages(self):
        for text in (
            "Mi nuevo correo es ana@nueva.example.",
            "Ma nouvelle adresse : luc@neuf.example",
            "Meine neue E-Mail-Adresse lautet kai@neu.example.",
            "Meu novo e-mail é bia@novo.example.",
            "Il mio nuovo indirizzo è gio@nuovo.example.",
            "Mijn nieuwe e-mailadres is joost@nieuw.example.",
        ):
            with self.subTest(text):
                self.assertEqual(named_contact(text, set())[1], "new_address")

    def test_letter_case_and_a_closing_full_stop_are_dropped(self):
        self.assertEqual(
            named_contact("Please contact Riley.Chen@Contoso.Example.", set()),
            ("riley.chen@contoso.example", "contact"),
        )

    def test_at_most_twenty_addresses_are_read(self):
        text = " ".join(f"user{index}@x{index}.example" for index in range(30)) + " please contact last@x.example"

        self.assertEqual(named_contact(text, set()), ("", ""))

    def test_hostile_text_is_read_in_bounded_time(self):
        text = "a" * 5000 + "@" + "b." * 3000 + "\n" + "On " + "x" * 5000 + " wrote:"

        self.assertEqual(named_contact(own_text(text), set()), ("", ""))


class LoopProtectionTests(SimpleTestCase):
    def test_an_automatic_reply_to_an_automatic_reply_stays_automated(self):
        verdict = verdict_of(samples.auto_reply_to_auto_reply())

        self.assertEqual((verdict.classification, verdict.subtype), ("auto_reply", "vacation"))
        self.assertIn("x-autoreply", verdict.signals)
        self.assertIn(REPLY_HINT, verdict.hints)

    def test_replying_to_the_sites_mail_never_makes_an_automatic_reply_a_persons(self):
        for name in ("exchange_oof_english", "exchange_oof_spanish", "left_with_contact", "auto_reply_to_auto_reply"):
            with self.subTest(name):
                self.assertTrue(verdict_of(getattr(samples, name)(), replies=True).automated)

    def test_rfc_3834_markers_forbid_an_automatic_response(self):
        for name, headers in {
            "auto-submitted": {"Auto-Submitted": "auto-replied"},
            "list": {"List-Id": "<x.example>"},
            "precedence": {"Precedence": "junk"},
            "suppress": {"X-Auto-Response-Suppress": "OOF, AutoReply"},
            "null return path": {"Return-Path": "<>"},
            "exchange rule": {"X-MS-Exchange-Inbox-Rules-Loop": "x@example.org"},
            "vendor": {"X-Autorespond": "yes"},
        }.items():
            with self.subTest(name):
                self.assertFalse(response_allowed(evidence(headers)))
        self.assertFalse(response_allowed(evidence(from_address="no-reply@service.example")))
        self.assertFalse(response_allowed(evidence(from_address="")))
        self.assertTrue(response_allowed(evidence({"Auto-Submitted": "no", "X-Auto-Response-Suppress": "DR, RN"})))

    def test_a_person_answering_from_a_crm_must_not_be_answered_automatically(self):
        verdict = verdict_of(samples.crm_reply_about_judging())

        self.assertEqual(verdict.classification, "human")
        self.assertIn(NO_AUTO_RESPONSE, verdict.hints)

    def test_a_plain_persons_message_may_be(self):
        verdict = classify(evidence(text_head="Can I judge this year?"), own_addresses=OWN)

        self.assertNotIn(NO_AUTO_RESPONSE, verdict.hints)

    def test_a_message_that_may_be_automated_or_forged_must_not_be_answered_automatically(self):
        # A responder that marks nothing would answer an acknowledgement with another: when unsure, never answer.
        for name, values in {
            "absence": {"text_head": "I am out of the office until Monday."},
            "left": {"text_head": "Jordan has left Contoso."},
            "acknowledgement": {"text_head": "We have received your request. Your ticket number is 4521."},
            "receipt": {"subject": "Read: Judges wanted"},
            "the site's address without proof": {"from_address": "i2g@ucmerced.edu"},
        }.items():
            with self.subTest(name):
                verdict = classify(evidence(**values), own_addresses=OWN)
                self.assertEqual(verdict.classification, "human")
                self.assertEqual(verdict.hints[0], NO_AUTO_RESPONSE)

    def test_the_no_answer_hint_comes_first_however_many_bulk_signals_follow(self):
        # The ticket keeps the first 20 signals: the hint must never be the one cut off.
        headers = {**dict.fromkeys(ESP_HEADERS, "1"), "List-Unsubscribe": "<mailto:x@x.example>"}
        verdict = classify(
            evidence(headers, text_head="I'm out of the office.", replies_to_site_mail=True), own_addresses=OWN
        )

        self.assertGreater(len(verdict.hints), 20)
        self.assertEqual(verdict.hints[:2], (REPLY_HINT, NO_AUTO_RESPONSE))
