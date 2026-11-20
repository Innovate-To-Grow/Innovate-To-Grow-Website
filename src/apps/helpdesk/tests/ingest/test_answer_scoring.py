"""What the scam checks make of an answer and of a proven sender, after the fourth live check of the admin:

- an answer is scored on what its sender wrote, whatever the order: a quote first (bottom-posted), "> " lines in
  between, or an HTML-only answer with its quote block; the phishing checks read the whole message, HTML included, so
  a raw-IP or deceptive link keeps a phish spam even under a quote;
- an answer Exchange rates as spam reaches staff, warned, rather than vanishing on the ticket;
- any one phishing signal (a shortener, hidden HTML) keeps a proven sender's phish spam;
- links rewritten by Proofpoint URL Defense (v2 and v3) are judged by where they go."""

from django.core.cache import cache
from django.test import TestCase

from ...models import Ticket, TicketMessage
from ...services import tickets
from .. import corpus
from ..helpers import helpdesk_staff, receive
from ..service.intake.scam_mail import DMARC_PASS, WORD_REASONS, locked_out

Status = Ticket.Status
Kind = TicketMessage.Kind
LEE = "Lee Kim <lee@example.org>"
PHISH = (
    "Your account has been suspended. Verify immediately within 24 hours: click here https://203.0.113.9/login and "
    "enter your password and bank account number."
)
DECEPTIVE = '<a href="https://evil-login.example/x">i2g.ucmerced.edu/verify</a>'
GMAIL_QUOTE = (
    '<div class="gmail_quote"><div class="gmail_attr">On Wed, Nov 11, 2026 at 10:00 AM Innovate to Grow wrote:<br>'
    '</div><blockquote class="gmail_quote">Hello Lee, your account has been unlocked. Click here on the sign-in page '
    "to reset your password within 24 hours.</blockquote></div>"
)


class _AnswerCase(TestCase):
    def setUp(self):
        cache.clear()
        self.ticket = receive(corpus.message(sender=LEE, subject="Cannot sign in", message_id="<lee-1@x.example>"))
        tickets.update_ticket(self.ticket, actor=helpdesk_staff(), status=Status.PENDING_CUSTOMER)
        Ticket.objects.filter(pk=self.ticket.pk).update(unread=False)
        self.subject = f"Re: Cannot sign in [{self.ticket.display_number}]"

    def answered(self, raw: bytes) -> TicketMessage:
        self.assertEqual(receive(raw).pk, self.ticket.pk)
        self.ticket.refresh_from_db()
        return self.ticket.messages.order_by("-occurred_at", "-created_at").first()

    def answer(self, text, **values) -> TicketMessage:
        return self.answered(corpus.message(sender=LEE, subject=self.subject, text=text, **values))


class AnswerWordsTests(_AnswerCase):
    def test_a_bottom_posted_phish_is_judged_on_its_own_words_and_link(self):
        message = self.answer(f"> Hello Lee, your account has been unlocked.\n\n{PHISH}", message_id="<lee-2@x>")

        self.assertEqual((message.kind, message.classification), (Kind.AUTOMATED, "spam"))
        self.assertIn("Contains 1 link(s) using raw IP addresses", message.scam_reasons)

    def test_a_bottom_posted_thanks_is_not_flagged(self):
        message = self.answer("> Hello Lee, your account has been unlocked: click here.\n\nThanks, it works now.")

        self.assertEqual((message.kind, message.scam_level), (Kind.CUSTOMER, "low"))
        self.assertEqual((self.ticket.status, self.ticket.unread), (Status.OPEN, True))

    def test_an_html_only_answer_leaves_out_its_quote_block(self):
        head = f"From: {LEE}\r\nTo: i2g@ucmerced.edu\r\nSubject: {self.subject}\r\nMessage-ID: <lee-3@x>\r\n"
        raw = f"{head}Content-Type: text/html; charset=utf-8\r\n\r\n<div>Thanks, it works now!</div>{GMAIL_QUOTE}"

        message = self.answered(raw.encode())

        self.assertEqual((message.kind, message.scam_level, message.scam_reasons), (Kind.CUSTOMER, "low", []))

    def test_a_deceptive_link_in_the_answers_html_keeps_it_spam(self):
        html = "<p>" + PHISH.replace("https://203.0.113.9/login", DECEPTIVE) + "</p>"

        message = self.answer(PHISH.replace("https://203.0.113.9/login", "i2g.ucmerced.edu/verify"), html=html)

        self.assertEqual(message.classification, "spam")
        self.assertIn("1 link(s) display a different domain than the actual URL", message.scam_reasons)

    def test_an_answer_exchange_rates_spam_reaches_staff_warned(self):
        message = self.answer("Yes: please add our second mentor too.", headers={"X-MS-Exchange-Organization-SCL": "5"})

        self.assertEqual((message.kind, message.scam_level), (Kind.CUSTOMER, "medium"))
        self.assertEqual(message.scam_reasons, ["Exchange rated it spam (SCL 5)"])
        self.assertEqual((self.ticket.status, self.ticket.unread, self.ticket.flags), (Status.OPEN, True, []))


class DecisiveSignalTests(TestCase):
    def setUp(self):
        cache.clear()

    def assertSpam(self, ticket, reason):
        message = ticket.messages.get()
        self.assertEqual((ticket.status, message.classification), (Status.SPAM, "spam"))
        self.assertIn(reason, message.scam_reasons)

    def test_a_shortener_alone_keeps_a_proven_senders_phish_spam(self):
        text = (
            "My account was locked and I cannot reset my password. Help immediately, within 24 hours: https://bit.ly/3x"
        )

        self.assertSpam(receive(locked_out(DMARC_PASS, text=text)), "Contains 1 shortened URL(s) (e.g. bit.ly)")

    def test_hidden_html_alone_does_too(self):
        raw = locked_out(DMARC_PASS, html='<p>Help</p><div style="display:none">x</div>')

        self.assertSpam(receive(raw), "HTML contains hidden elements (display:none / visibility:hidden)")

    def test_links_through_proofpoint_url_defense_are_judged_by_where_they_go(self):
        wrapped = {
            "v3": "https://urldefense.com/v3/__https://www.ucmerced.edu/account__;!!Mih3wA!abcDEF$",
            "v2": "https://urldefense.proofpoint.com/v2/url?u=https-3A__www.ucmerced.edu_account&amp;d=DwMFaQ&amp;c=x",
        }
        for index, (version, href) in enumerate(wrapped.items()):
            with self.subTest(version):
                html = f'<p>Reset it at <a href="{href}">https://www.ucmerced.edu/account</a></p>'
                ticket = receive(locked_out(DMARC_PASS, html=html, message_id=f"<pp-{index}@mail.example.org>"))

                message = ticket.messages.get()
                self.assertEqual(
                    (ticket.status, message.scam_level, message.scam_reasons), (Status.NEW, "medium", WORD_REASONS)
                )
