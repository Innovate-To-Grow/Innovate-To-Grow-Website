import base64
import quopri
from email.message import EmailMessage
from email.policy import SMTP

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase

from apps.core.services.email.inbound import LINK_PLACEHOLDER as REMOVED

from ...services.ingest.reading.parse import parse
from .. import corpus
from ..helpers import receive
from ..intake.test_signin_file_edges import SITE_HOSTS, SMS

SAVED = corpus.message(sender="Portal <noreply@i2g.example>", subject="Your sign-in link 登录", text="Your links: here")
TOKEN = "Qm7Tz2LoGiNaaa9KxW4vB8nR1sY6uE3cH5jF0dP_gA-kLzX2wQ7eR9tY4uI1oP6a"  # as long as the site's: token_urlsafe(48)
LINK = f"https://i2g.ucmerced.edu/login-link#token={TOKEN}"


def with_attached(body: bytes, encoding: str) -> bytes:
    """A message carrying ``body`` as a message/rfc822 part sent in ``encoding`` (RFC 2046 allows 7bit, 8bit, binary)."""
    head = (
        b"From: Sam <sam@example.org>\r\nContent-Type: multipart/mixed; boundary=b\r\n\r\n--b\r\n\r\nSee attached.\r\n"
    )
    part = f"--b\r\nContent-Type: message/rfc822\r\nContent-Transfer-Encoding: {encoding}\r\n\r\n".encode()
    return head + part + body + b"\r\n--b--\r\n"


def forwarding_quoted_printable(name: str) -> bytes:
    """A person forwarding the sign-in email ``name`` sent, attached as message/rfc822 the way Python's email library
    writes it when asked for quoted-printable: the saved message's line breaks encoded too (=0D=0A), and a soft line
    break ("=" at the end of a line) at most 76 characters apart, wherever it falls (inside the links)."""
    saved = EmailMessage(policy=SMTP)
    saved["From"] = f"{name} <noreply@i2g.example> {LINK}"
    saved["To"] = "sam@example.org"
    saved["Subject"] = f"Your sign-in link for the showcase portal {SMS} 登录"
    saved.set_content(
        f"Please use this sign-in link to get into the showcase portal right away: {LINK}, thanks\n"
        f"The text message I got on my phone yesterday evening had this other link: {SMS} 请帮忙\n"
    )
    mail = EmailMessage(policy=SMTP)
    mail["From"] = "Sam Saved <sam.saved@example.org>"
    mail["To"] = corpus.SITE
    mail["Subject"] = f"FW: the sign-in email {name} sent"
    mail["Message-ID"] = f"<saved-qp-{len(name)}@example.org>"
    mail.set_content("Please see the attached email.")
    mail.add_attachment(
        saved.as_bytes(), maintype="message", subtype="rfc822", filename="signin.eml", cte="quoted-printable"
    )
    return mail.as_bytes()


class BodyTests(SimpleTestCase):
    def test_an_html_only_message_gives_its_text_for_the_classifier(self):
        raw = (
            b"From: a@example.org\r\nSubject: hi\r\nContent-Type: text/html; charset=utf-8\r\n\r\n"
            b"<p>I am <b>out of the office</b></p>"
        )

        parsed = parse(raw)

        self.assertEqual(parsed.text, "")
        self.assertIn("out of the office", parsed.text_head())

    def test_nul_characters_are_dropped_so_the_message_can_be_stored(self):
        # PostgreSQL text cannot hold NUL; a UTF-16 part labelled as plain text decodes to a NUL after every letter.
        raw = (
            b"From: a@example.org\r\nMessage-ID: <n\x00ul@x>\r\nContent-Type: text/plain\r\n"
            b"Content-Transfer-Encoding: base64\r\n\r\n" + base64.encodebytes("Hello from a person".encode("utf-16-le"))
        )

        parsed = parse(raw)

        self.assertEqual((parsed.text, parsed.message_id), ("Hello from a person", "<nul@x>"))
        html = parse(corpus.message(text="plain\x00text", html="<p>rich\x00text</p>"))
        self.assertEqual((html.text, html.html), ("plaintext\n", "<p>richtext</p>\n"))

    def test_unknown_charsets_and_bad_bytes_are_decoded_with_replacements(self):
        raw = b"From: a@example.org\r\nContent-Type: text/plain; charset=x-unknown\r\n\r\ncaf\xe9"

        self.assertEqual(parse(raw).text, "caf�")

    def test_text_in_a_codec_no_mail_program_writes_is_read_as_utf_8(self):
        # Punycode decodes in quadratic time: a crafted 4 MB body would stall the import for minutes.
        for charset in ("punycode", "unicode-escape"):
            with self.subTest(charset):
                raw = f"From: a@example.org\r\nContent-Type: text/plain; charset={charset}\r\n\r\n".encode()

                self.assertEqual(parse(raw + rb"Thanks-for the help A").text, r"Thanks-for the help A")

    def test_report_parts_are_neither_body_nor_attachment(self):
        parsed = parse(corpus.read_receipt())

        self.assertEqual((parsed.content_type, parsed.report_type), ("multipart/report", "disposition-notification"))
        self.assertIn("was read", parsed.text)
        self.assertEqual(parsed.attachments, [])

    def test_calendar_parts_are_noticed_and_kept_as_files(self):
        parsed = parse(corpus.calendar_reply())

        self.assertTrue(parsed.has_calendar)
        self.assertEqual([item.content_type for item in parsed.attachments], ["text/calendar"])
        self.assertTrue(parsed.attachments[0].filename.startswith("attachment-1"))


class EncodedAttachedMessageTests(TestCase):
    """RFC 2046 forbids base64 and quoted-printable for message/rfc822, yet Python's email library writes base64 (and
    quoted-printable when asked, and some clients do): the part is decoded from its encoded text as it came and read
    like a forward, or counted as not readable."""

    def setUp(self):
        cache.clear()

    def test_a_message_attached_base64_by_pythons_email_library_is_read(self):
        mail = EmailMessage(policy=SMTP)
        mail["From"] = "Sam Saved <sam.saved@example.org>"
        mail.set_content("The sign-in email I got is attached.")
        mail.add_attachment(SAVED, maintype="message", subtype="rfc822", filename="signin.eml")
        self.assertIn(b"Content-Type: message/rfc822\r\nContent-Transfer-Encoding: base64", mail.as_bytes())

        parsed = parse(mail.as_bytes())

        (attached,) = parsed.attached_messages
        self.assertEqual(
            (attached["from"], attached["subject"]), ("Portal <noreply@i2g.example>", "Your sign-in link 登录")
        )
        self.assertEqual((attached["text"].strip(), parsed.attached_dropped), ("Your links: here", 0))

    def test_a_quoted_printable_one_is_read_and_one_without_headers_is_counted(self):
        quoted = parse(with_attached(quopri.encodestring(SAVED), "quoted-printable"))

        self.assertEqual([item["subject"] for item in quoted.attached_messages], ["Your sign-in link 登录"])
        for encoding, encode in (("base64", base64.encodebytes), ("quoted-printable", quopri.encodestring)):
            with self.subTest(encoding):
                headless = parse(with_attached(encode(b"Only some words, no headers.\r\n"), encoding))

                self.assertEqual((headless.attached_messages, headless.attached_dropped), ([], 1))

    @SITE_HOSTS
    def test_one_attached_quoted_printable_as_python_writes_it_is_read_whole_and_keeps_no_token(self):
        # Python's parser reads the encoded text as a message: the first line was taken for the From header, cut
        # inside the link at its soft line break, and the rest (the real headers, and the body still quoted-printable)
        # was stored, the tokens readable across the breaks. With the longer name a line starts with the link's ":",
        # which the parser drops while it reads headers: the text cannot be rebuilt from what it kept either.
        long_name = "Innovate-to-Grow-Showcase-Portal-UC"
        self.assertIn(b"https=\r\n://i2g.", forwarding_quoted_printable(long_name))
        for name in ("Portal", long_name):
            with self.subTest(name):
                message = receive(forwarding_quoted_printable(name)).messages.get()

                (attached,) = message.attached_messages
                self.assertEqual(
                    (attached["from"], attached["subject"]),
                    (
                        f"{name} <noreply@i2g.example> {REMOVED}",
                        f"Your sign-in link for the showcase portal {REMOVED} 登录",
                    ),
                )
                self.assertEqual(
                    attached["text"].strip(),
                    f"Please use this sign-in link to get into the showcase portal right away: {REMOVED}, thanks\n"
                    f"The text message I got on my phone yesterday evening had this other link: {REMOVED} 请帮忙",
                )
                stored = f"{message.subject} {message.body_text} {message.attached_messages}"
                for token in (TOKEN, SMS.rsplit("/", 1)[1]):  # a soft line break falls inside a token once at most
                    self.assertNotIn(token[: len(token) // 2], stored)
                    self.assertNotIn(token[len(token) // 2 :], stored)
