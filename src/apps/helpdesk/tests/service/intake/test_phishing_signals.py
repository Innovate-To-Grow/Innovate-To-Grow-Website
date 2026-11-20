"""Phishing signals, proof of the sender and the reasons kept, after the third live check of the admin:

- a brand's name in a person's name (Chase Lee) and a web form's missing display name are no phishing signals:
  authenticated mail scoring high on its words stays a person's ticket, flagged suspicious;
- mail Exchange marks internal to the organisation proves its sender as DMARC does (a colleague's urgent request is a
  person's ticket, and is acknowledged); the marker proves nothing below the server's own;
- a proven sender whose words alone score medium is not flagged (a person asking how to reset their password);
- a sender imitating the site's own domain (ucrnerced.edu) is a look-alike: spam however authenticated;
- the five reasons kept are those that weigh most, a phishing signal always among them;
- Microsoft Safe Links are unwrapped before the link checks: a link through Microsoft's wrapper is no mismatch."""

from django.test import override_settings

from ....models import TicketMessage
from ... import corpus
from ...helpers import receive
from ...helpers.service import sending_settings
from .scam_mail import DMARC_PASS, WORD_REASONS, locked_out
from .test_scam_verdict import _VerdictCase

INTERNAL = {
    "X-MS-Exchange-Organization-AuthAs": "Internal",
    "Authentication-Results": "dkim=none (message not signed) header.d=none;dmarc=none action=none header.from=ucmerced.edu",
}
COLLEAGUE = "Casey Colleague <casey.colleague@ucmerced.edu>"
MISMATCH = "1 link(s) display a different domain than the actual URL"
SAFE_LINK = (
    "https://nam02.safelinks.protection.outlook.com/?url=https%3A%2F%2Fwww.ucmerced.edu%2Faccount&amp;data=05%7C01"
    "&amp;reserved=0"
)


class NoPhishingSignalTests(_VerdictCase):
    def test_a_brand_in_a_persons_name_is_none(self):
        ticket = receive(locked_out(DMARC_PASS, sender="Chase Lee <chase.lee@example.org>"))

        self.assertSuspiciousPersonsTicket(
            ticket, reasons=['Display name mentions "Chase" but email domain is example.org', *WORD_REASONS]
        )

    def test_a_web_forms_missing_display_name_and_reply_to_are_none(self):
        raw = locked_out(DMARC_PASS, sender="forms@relay.example", headers={"Reply-To": "sam@example.edu"})

        reasons = ["Sender has no display name", *WORD_REASONS]
        self.assertSuspiciousPersonsTicket(
            receive(raw),
            reasons=[*reasons, "Reply-To domain (example.edu) differs from the sender domain (relay.example)"],
        )

    def test_a_safe_links_wrapper_is_no_mismatch(self):
        html = f'<p>Reset it at <a href="{SAFE_LINK}">https://www.ucmerced.edu/account</a></p>'

        self.assertSuspiciousPersonsTicket(receive(locked_out(DMARC_PASS, html=html)))


class ProofTests(_VerdictCase):
    def test_exchange_marking_mail_internal_proves_the_sender(self):
        ticket = receive(locked_out(sender=COLLEAGUE, headers=INTERNAL))

        self.assertSuspiciousPersonsTicket(ticket)
        self.assertEqual(ticket.messages.get().auth_summary["authas"], "internal")

    def test_the_marker_proves_nothing_below_the_servers_own(self):
        raw = locked_out(sender=COLLEAGUE, headers={**INTERNAL, "X-MS-Exchange-Organization-AuthAs": "Anonymous"})
        head, body = raw.split(b"\r\n\r\n", 1)

        ticket = receive(head + b"\r\nX-MS-Exchange-Organization-AuthAs: Internal\r\n\r\n" + body)

        self.assertSpam(ticket)
        self.assertNotIn("authas", ticket.messages.get().auth_summary)

    @override_settings(BACKGROUND_JOBS_ENABLED=True)
    def test_a_colleague_is_acknowledged(self):
        sending_settings(send_acknowledgement=True)
        with self.captureOnCommitCallbacks(execute=True):
            ticket = receive(corpus.message(sender=COLLEAGUE, headers=INTERNAL))

        acknowledged = ticket.messages.filter(kind=TicketMessage.Kind.REPLY, automatic=True)
        self.assertEqual(list(acknowledged.values_list("to_addresses", flat=True)), [["casey.colleague@ucmerced.edu"]])

    def test_a_proven_senders_password_question_is_not_flagged(self):
        question = {"subject": "Forgot my password", "text": "Hi, I forgot my password. How do I reset it?"}
        proven = receive(corpus.message(headers={"Authentication-Results": DMARC_PASS}, **question))
        unproven = receive(corpus.message(message_id="<unproven@mail.example.org>", **question))

        self.assertEqual((proven.flags, proven.messages.get().scam_level), ([], "low"))
        self.assertEqual(proven.messages.get().scam_reasons, [])
        self.assertEqual((unproven.flags, unproven.messages.get().scam_level), (["suspicious"], "medium"))


class LookalikeAndReasonTests(_VerdictCase):
    def test_a_sender_imitating_the_sites_own_domain_stays_spam(self):
        ticket = receive(locked_out(DMARC_PASS, sender="UC Merced IT <it@ucrnerced.edu>"))
        genuine = receive(locked_out(DMARC_PASS, sender="IT <it@ucmerced.edu>", message_id="<genuine@ucmerced.edu>"))

        self.assertSpam(
            ticket, ['Domain "ucrnerced.edu" imitates "ucmerced" using look-alike characters', *WORD_REASONS]
        )
        self.assertSuspiciousPersonsTicket(genuine)

    def test_the_reasons_kept_are_the_weightiest_with_the_phishing_signal(self):
        text = (
            "Dear customer, your account has been suspended. Pay the $5,000 fee and $2,000 deposit "
            "immediately, within 24 hours, and confirm your password."
        )
        html = '<p>Reset it at <a href="https://reset-portal.example/ucm">https://www.ucmerced.edu/account</a></p>'

        message = receive(locked_out(DMARC_PASS, text=text, html=html)).messages.get()

        self.assertEqual(message.scam_level, "high")
        self.assertEqual(len(message.scam_reasons), 5)
        self.assertIn(MISMATCH, message.scam_reasons)
        self.assertNotIn('Uses generic greeting (e.g. "Dear Customer")', message.scam_reasons)  # it weighs least
