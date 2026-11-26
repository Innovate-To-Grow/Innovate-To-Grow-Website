"""The messages a person attaches (forwards, saved ``.eml`` files) are read to a summary within the limits: at most
``MAX_ATTACHED_MESSAGES`` of them, never their own attachments. One past the limit, one that cannot be read and one
attached inside an attached message are counted and named on the message's card (the original is in Outlook) instead
of vanishing, and the message is not said to be cut off. One sent as HTML only reads as its sanitized HTML laid out
as a mail program shows it, so its personal links go as in a message's own HTML (also one that inline formatting
splits). A body part whose payload is not bytes reads as no text."""

from email import message_from_bytes
from email.message import EmailMessage
from email.policy import SMTP
from html import escape

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.core.services.email.inbound import LINK_PLACEHOLDER as REMOVED

from ....services.ingest.reading import mime as parsing
from ....services.ingest.reading.message import MAX_ATTACHED_MESSAGES
from ....services.ingest.reading.parse import parse
from ... import corpus
from ...helpers import helpdesk_staff, receive
from ...intake.test_signin_file_edges import SITE_HOSTS, SMS
from .test_signin_links_in_files import DOC, LINK, SAVED, mail_with


def forwarding(count: int, *, inner_attachments=()) -> bytes:
    """A person forwarding ``count`` messages as attachments."""
    outer = EmailMessage(policy=SMTP)
    outer["From"] = "Pat Doe <pat@example.org>"
    outer["To"] = corpus.SITE
    outer["Subject"] = "Fwd: the earlier messages"
    outer["Message-ID"] = "<fwd-many@mail.example.org>"
    outer.set_content("See the messages below.")
    for index in range(count):
        inner = corpus.message(
            subject=f"Inner {index}", message_id=f"<inner-{index}@mail.example.org>", attachments=inner_attachments
        )
        outer.add_attachment(message_from_bytes(inner, policy=SMTP))
    return outer.as_bytes()


def saved(subject: str, body: str, subtype: str = "plain") -> EmailMessage:
    """A message the site sent, as a person saves or forwards it."""
    message = EmailMessage(policy=SMTP)
    message["From"] = "Portal <noreply@i2g.example>"
    message["Subject"] = subject
    message.set_content(body, subtype=subtype)
    return message


def attaching(inner: EmailMessage, **how) -> bytes:
    """A person's message with ``inner`` attached (as Outlook forwards one, unless ``how`` says otherwise)."""
    mail = EmailMessage(policy=SMTP)
    mail["From"] = "Hal Forward <hal@example.org>"
    mail["To"] = corpus.SITE
    mail.set_content("Please see the attached email.")
    mail.add_attachment(inner.as_bytes() if how else inner, filename="forwarded.eml", **how)
    return mail.as_bytes()


class AttachedMessageTests(SimpleTestCase):
    def test_at_most_the_cap_of_attached_messages_is_summarized(self):
        parsed = parse(forwarding(MAX_ATTACHED_MESSAGES + 2))

        self.assertEqual(
            [item["subject"] for item in parsed.attached_messages],
            [f"Inner {index}" for index in range(MAX_ATTACHED_MESSAGES)],
        )
        self.assertEqual(parsed.attachments, [])

    def test_an_attached_messages_own_attachments_are_not_kept(self):
        parsed = parse(forwarding(1, inner_attachments=[("report.pdf", b"%PDF-1.7 data", "application/pdf")]))

        (attached,) = parsed.attached_messages
        self.assertEqual(attached["subject"], "Inner 0")
        self.assertIn("showcase", attached["text"])
        self.assertEqual(parsed.attachments, [])

    def test_a_message_attached_inside_an_attached_message_is_counted_as_not_shown(self):
        # The inner one was read into a summary nobody kept: neither shown nor counted, so staff could not tell that
        # the forward carried another message. Attached as a part (here quoted-printable) or saved as an .eml file.
        middle = saved("MIDDLE", "Forwarding the inner one.")
        inner = saved("INNER", f"Sign in: {LINK}").as_bytes()
        middle.add_attachment(inner, maintype="message", subtype="rfc822", filename="inner.eml", cte="quoted-printable")
        middle.add_attachment(inner, maintype="application", subtype="octet-stream", filename="saved.eml")

        parsed = parse(attaching(middle, maintype="message", subtype="rfc822", cte="base64"))

        self.assertEqual([item["subject"] for item in parsed.attached_messages], ["MIDDLE"])
        self.assertEqual((parsed.attached_dropped, parsed.incomplete), (2, False))

    @SITE_HOSTS
    def test_one_sent_as_html_only_reads_as_its_sanitized_html_a_line_per_paragraph(self):
        # Read with a line break at every element, a link Word's spelling marks split became lines too short to be
        # judged (the SMS and unsubscribe tokens stayed whole, the sign-in token's tail too), and every link or bold
        # word stood on a line of its own.
        site, sms = SMS.rsplit("/", 1)
        stop, unsubscribe = corpus.UNSUBSCRIBE_LINK.rstrip("/").rsplit("/", 1)
        html = (
            "<html><head><style>p.MsoNormal{margin:0}</style></head><body><p class=MsoNormal>Hello Sam,</p>"
            f"<p class=MsoNormal>Your text link: {site}/<span class=SpellE>{sms}</span> (from the SMS).</p>"
            f"<p class=MsoNormal>Sign in: {LINK[:-6]}<span class=SpellE>{LINK[-6:]}</span></p>"
            f"<p class=MsoNormal>Stop: {stop}/<span class=SpellE>{unsubscribe}</span>/</p>"
            f'<p class=MsoNormal>Or <a href="{escape(LINK)}">sign in here</a>, the agenda is in <a href="{DOC}">the '
            "shared doc</a>.</p><p class=MsoNormal><o:p>&nbsp;</o:p></p>"  # Outlook's empty line
            "<p class=MsoNormal>Thanks, <b>Portal</b> team</p>"
        )

        (attached,) = parse(attaching(saved("Your links (HTML only)", html, "html"))).attached_messages

        self.assertEqual(
            attached["text"],
            f"Hello Sam,\nYour text link: {REMOVED} (from the SMS).\nSign in: {REMOVED}\nStop: {REMOVED}\n"
            f"Or sign in here {REMOVED}, the agenda is in the shared doc.\n\nThanks, Portal team",
        )

    def test_a_body_part_whose_payload_is_not_bytes_reads_as_no_text(self):
        class Part:
            def get_payload(self, decode=False):
                return None

        self.assertEqual(parsing._decode_text(Part()), "")


class SavedMessageTests(TestCase):
    def test_saved_messages_past_the_limit_or_unreadable_are_counted_not_taken_for_a_cut(self):
        many = [(f"booth-{number}.eml", SAVED, "application/octet-stream", {}) for number in range(7)]
        within = many[:MAX_ATTACHED_MESSAGES]

        past, empty, fine = (
            parse(mail_with(*many)),
            parse(mail_with(("empty.eml", b"", "application/octet-stream", {}))),
            parse(mail_with(*within)),
        )

        self.assertEqual(
            (len(past.attached_messages), past.attached_dropped, past.incomplete), (MAX_ATTACHED_MESSAGES, 2, False)
        )
        self.assertEqual((empty.attached_dropped, empty.incomplete), (1, False))
        self.assertEqual((len(fine.attached_messages), fine.attached_dropped), (MAX_ATTACHED_MESSAGES, 0))

    def test_the_card_names_the_saved_messages_left_out(self):
        cache.clear()
        self.client.force_login(helpdesk_staff())
        many = [(f"booth-{number}.eml", SAVED, "application/octet-stream", {}) for number in range(7)]
        ticket = receive(mail_with(*many))

        page = self.client.get(reverse("admin:helpdesk_ticket_change", args=[ticket.pk]))

        self.assertContains(
            page, "2 more attached messages are not shown (more than five, inside another attached message, or not"
        )
        self.assertNotContains(page, "This message was cut off here")
