from django.test import SimpleTestCase

from apps.core.services.email.inbound import NO_AUTO_RESPONSE, REPLY_HINT, classify
from apps.core.services.email.inbound.classification.autoreply import named_contact, own_text, response_allowed
from apps.core.services.email.inbound.classification.rules import ESP_HEADERS
from apps.core.tests.services.email.inbound.auto_replies.test_auto_replies import verdict_of

from .. import samples
from ..classify.test_classify import OWN, evidence


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
