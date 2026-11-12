"""Automatic replies, on the synthetic samples: out-of-office replies (English and Spanish, with and without the
subject prefix), left-the-organisation notices (naming a contact, a new address, nothing; in Spanish; an Exchange
rule's reply), the quoted original never deciding anything, the address a notice names, and the loop protection: an
automatic reply stays automated whatever it answers, and a message that must not be answered automatically says so.
Pure: no database."""

from django.test import SimpleTestCase

from apps.core.services.email.inbound import NO_AUTO_RESPONSE, REPLY_HINT, classify
from apps.core.services.email.inbound.autoreply import kind_of, named_contact, own_subject, own_text, response_allowed

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

    def test_a_mailbox_nobody_reads_is_left_only_without_an_absence(self):
        self.assertEqual(kind_of("This mailbox is not monitored."), "left_org")
        self.assertEqual(kind_of("This mailbox is not monitored until we return on January 5."), "vacation")
        self.assertEqual(kind_of("Thanks for writing."), "other")

    def test_a_person_writing_that_they_left_stays_a_person_with_a_hint(self):
        verdict = classify(
            evidence(text_head="Hi! I have left Contoso; my new email address is pat@new.example."),
            own_addresses=OWN,
        )

        self.assertEqual((verdict.classification, verdict.contact), ("human", ""))
        self.assertIn("possible_left_org", verdict.hints)


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
