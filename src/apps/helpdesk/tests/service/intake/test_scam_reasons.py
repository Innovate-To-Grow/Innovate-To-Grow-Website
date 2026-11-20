"""Why the scam checks warned, kept for staff: at most five reasons (each cut to 200 characters with its prefix) stored
among the message's signals as "scam: <reason>" for a medium or high score (a low one keeps none), listed by
``TicketMessage.scam_reasons``, and shown on the ticket page ("Why: …") on the suspicious and on the spam card."""

from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from ....models import TicketMessage
from ... import corpus
from ...helpers import helpdesk_staff, receive
from .scam_mail import DMARC_PASS, SCAM, WORD_REASONS, locked_out, scam_signals

ANALYZE = "apps.helpdesk.services.ingest.routing.classify.analyze_email"
SUSPICIOUS = "Suspicious: the scam checks found warning signs."
SPAM = "Marked as spam by the scam checks."
WHY = f"Why: {'; '.join(WORD_REASONS)}."


class StoredReasonsTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_the_reasons_are_kept_among_the_signals_after_the_classifiers_own(self):
        message = receive(locked_out(DMARC_PASS)).messages.get()

        self.assertEqual(scam_signals(message), [f"{SCAM}{reason}" for reason in WORD_REASONS])
        self.assertEqual(message.signals[-len(WORD_REASONS) :], scam_signals(message))
        self.assertEqual(message.scam_reasons, WORD_REASONS)

    def test_at_most_five_reasons_each_cut_to_200_characters(self):
        reasons = ["R" * 300, *(f"Reason {number}" for number in range(2, 9))]

        for level in ("medium", "high"):
            with self.subTest(level), patch(ANALYZE, return_value={"risk_level": level, "reasons": reasons}):
                message = receive(corpus.message(message_id=f"<{level}@mail.example.org>")).messages.get()

                self.assertEqual(message.scam_level, level)
                self.assertEqual([len(item) for item in scam_signals(message)], [200, 14, 14, 14, 14])
                self.assertEqual(message.scam_reasons, ["R" * 194, "Reason 2", "Reason 3", "Reason 4", "Reason 5"])

    def test_a_low_score_keeps_no_reasons(self):
        # A sender without a display name is one finding (1 point): a low score, nothing to warn about.
        message = receive(corpus.message(sender="pat@example.org")).messages.get()

        self.assertEqual(message.scam_level, "low")
        self.assertEqual((scam_signals(message), message.scam_reasons), ([], []))


class ScamReasonsPropertyTests(SimpleTestCase):
    def test_only_the_signals_with_the_prefix_and_without_it(self):
        message = TicketMessage(signals=["no_auto_response", "scam: First", "scam:no space", 7, "scam: Second"])

        self.assertEqual(message.scam_reasons, ["First", "Second"])
        self.assertEqual(TicketMessage(signals=None).scam_reasons, [])
        self.assertEqual(TicketMessage().scam_reasons, [])


class TicketPageTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client.force_login(helpdesk_staff())

    def page(self, ticket):
        response = self.client.get(reverse("admin:helpdesk_ticket_change", args=[ticket.pk]))
        self.assertEqual(response.status_code, 200)
        return response

    def test_the_suspicious_card_says_why(self):
        response = self.page(receive(locked_out(DMARC_PASS)))

        self.assertContains(response, SUSPICIOUS, count=1)
        self.assertContains(response, WHY, count=1)
        self.assertNotContains(response, SPAM)

    def test_the_spam_card_says_why(self):
        response = self.page(receive(locked_out()))

        self.assertContains(response, SPAM, count=1)
        self.assertContains(response, WHY, count=1)
        self.assertNotContains(response, SUSPICIOUS)

    def test_a_reason_is_shown_as_text_never_as_markup(self):
        # The look-alike reason quotes the sender's domain, which the sender chose.
        response = self.page(receive(locked_out(DMARC_PASS, sender="Pat Doe <pat@amaz0n.example>")))

        self.assertContains(response, SPAM)
        self.assertContains(
            response, "Why: Domain &quot;amaz0n.example&quot; imitates &quot;amazon&quot; using look-alike characters; "
        )

    def test_a_low_score_shows_no_warning(self):
        response = self.page(receive(corpus.message()))

        self.assertNotContains(response, "the scam checks")
        self.assertNotContains(response, "Why: ")
