"""The scam verdict on a person's mail (``classify_message``): a high score on mail whose sender proved their domain
(DMARC, or Exchange's composite authentication) gives a person's ticket flagged suspicious, unless phishing signals
(a look-alike sender domain, links that hide where they go, hidden HTML, failed authentication) reach the medium
threshold on their own; a Reply-To or Return-Path elsewhere (a web form, a mailing service) is no such signal. Without
that proof such mail stays spam. A person locked out of their account reads like a phish: such mail used to be spam
however it was authenticated. Microsoft Graph is never contacted."""

from django.core.cache import cache
from django.test import TestCase

from ....models import Ticket, TicketMessage
from ...helpers import receive
from .scam_mail import COMPAUTH_PASS, DMARC_PASS, UNPROVEN, WORD_REASONS, below_the_server, locked_out

Status = Ticket.Status
REPLY_TO_ELSEWHERE = "Reply-To domain (home.example) differs from the sender domain (example.org)"
RETURN_PATH_ELSEWHERE = "Return-Path domain (mailer.example) differs from the sender domain (example.org)"
DMARC_FAILED = "Email failed DMARC authentication (sender is likely spoofed)"
SPF_FAILED = "Email failed SPF authentication (sending server is not authorized)"


class _VerdictCase(TestCase):
    def setUp(self):
        cache.clear()

    def assertSuspiciousPersonsTicket(self, ticket, reasons=WORD_REASONS):
        message = ticket.messages.get()
        self.assertEqual(
            (ticket.status, ticket.automated, ticket.classification, ticket.flags, ticket.unread),
            (Status.NEW, False, "human", ["suspicious"], True),
        )
        self.assertEqual((message.kind, message.scam_level), (TicketMessage.Kind.CUSTOMER, "medium"))
        self.assertNotIn("scam_score_high", message.signals)
        self.assertEqual(message.scam_reasons, reasons)

    def assertSpam(self, ticket, reasons=WORD_REASONS):
        message = ticket.messages.get()
        self.assertEqual(
            (ticket.status, ticket.automated, ticket.classification, ticket.unread), (Status.SPAM, True, "spam", False)
        )
        self.assertEqual(
            (message.kind, message.scam_level, message.subtype), (TicketMessage.Kind.AUTOMATED, "high", "scam_score")
        )
        self.assertIn("scam_score_high", message.signals)
        self.assertEqual(message.scam_reasons, reasons)


class AuthenticatedSenderTests(_VerdictCase):
    def test_a_dmarc_pass_makes_mail_scoring_high_on_its_words_a_suspicious_persons_ticket(self):
        ticket = receive(locked_out(DMARC_PASS))

        self.assertSuspiciousPersonsTicket(ticket)
        self.assertEqual(ticket.messages.get().auth_summary["dmarc"], "pass")

    def test_a_composite_authentication_pass_does_too_without_a_dmarc_record(self):
        ticket = receive(locked_out(COMPAUTH_PASS))

        self.assertSuspiciousPersonsTicket(ticket)
        summary = ticket.messages.get().auth_summary
        self.assertEqual((summary["dmarc"], summary["compauth"]), ("bestguesspass", "pass"))

    def test_a_reply_to_and_return_path_elsewhere_are_no_phishing_signals(self):
        # A web form or a mailing service: 2 + 1 points, past the medium threshold, yet nothing hides where mail goes.
        cases = {
            "a Reply-To on another domain": ({"Reply-To": "Pat <pat.doe@home.example>"}, [REPLY_TO_ELSEWHERE]),
            "and a Return-Path too": (
                {"Reply-To": "pat.doe@home.example", "Return-Path": "<bounce@mailer.example>"},
                [REPLY_TO_ELSEWHERE, RETURN_PATH_ELSEWHERE],
            ),
        }
        for index, (case, (headers, alignment)) in enumerate(cases.items()):
            with self.subTest(case):
                raw = locked_out(DMARC_PASS, headers=headers, message_id=f"<aligned-{index}@mail.example.org>")

                self.assertSuspiciousPersonsTicket(receive(raw), reasons=[*WORD_REASONS, *alignment])


class UnprovenSenderTests(_VerdictCase):
    def test_the_same_mail_without_proof_of_the_senders_domain_stays_spam(self):
        unproven = {
            "no Authentication-Results": (locked_out(), WORD_REASONS),
            "SPF and DKIM pass only": (
                locked_out("spf=pass smtp.mailfrom=example.org; dkim=pass header.d=example.org"),
                WORD_REASONS,
            ),
            "a DMARC best guess and a composite soft pass": (
                locked_out(COMPAUTH_PASS.replace("compauth=pass reason=109", "compauth=softpass reason=201")),
                WORD_REASONS,
            ),
            # Exchange adds its own header on top: a pass the sender wrote below it proves nothing.
            "a pass forged below the server's results": (
                below_the_server(locked_out(UNPROVEN), "dmarc=pass action=none;compauth=pass reason=100"),
                WORD_REASONS,
            ),
            "a DMARC failure": (
                locked_out(UNPROVEN.replace("spf=none", "spf=fail").replace("dmarc=none", "dmarc=fail")),
                [*WORD_REASONS, DMARC_FAILED, SPF_FAILED],
            ),
        }
        for index, (case, (raw, reasons)) in enumerate(unproven.items()):
            with self.subTest(case):
                raw = raw.replace(b"<locked-1@", f"<unproven-{index}@".encode(), 1)

                self.assertSpam(receive(raw), reasons)


class TechnicalWarningTests(_VerdictCase):
    def test_authenticated_mail_with_a_technical_warning_stays_spam(self):
        link = '<p>Reset it at <a href="https://reset-portal.example/ucm">https://www.ucmerced.edu/account</a></p>'
        hidden = '<p>Help</p><span style="display: none">x</span><span style="font-size: 0">y</span>'
        warnings = {
            "a link whose text names another domain": (
                {"html": link},
                [*WORD_REASONS, "1 link(s) display a different domain than the actual URL"],
            ),
            "a look-alike sender domain": (
                {"sender": "Pat Doe <pat@amaz0n.example>"},
                ['Domain "amaz0n.example" imitates "amazon" using look-alike characters', *WORD_REASONS],
            ),
            "hidden HTML": (
                {"html": hidden},
                [
                    *WORD_REASONS,
                    "HTML contains hidden elements (display:none / visibility:hidden)",
                    "HTML contains zero-size text (font-size:0)",
                ],
            ),
        }
        for index, (case, (values, reasons)) in enumerate(warnings.items()):
            with self.subTest(case):
                raw = locked_out(DMARC_PASS, message_id=f"<technical-{index}@mail.example.org>", **values)

                self.assertSpam(receive(raw), reasons)

    def test_a_dmarc_failure_that_composite_authentication_overrode_stays_spam(self):
        # Exchange can pass a message that failed DMARC (a forward it trusts, reason 130): the failure still counts.
        auth = DMARC_PASS.replace("dmarc=pass", "dmarc=fail") + ";compauth=pass reason=130"

        ticket = receive(locked_out(auth))

        self.assertEqual(ticket.messages.get().auth_summary["compauth"], "pass")
        self.assertSpam(ticket, [*WORD_REASONS, DMARC_FAILED])
