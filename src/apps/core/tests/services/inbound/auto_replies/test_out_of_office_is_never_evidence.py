from django.test import SimpleTestCase

from apps.core.services.email.inbound import classify
from apps.core.services.email.inbound.autoreply import kind_of, own_subject, own_text
from apps.core.tests.services.inbound.auto_replies.test_auto_replies import OUT_OF_OFFICE, verdict_of

from .. import samples
from ..classify.test_classify import OWN, evidence


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
