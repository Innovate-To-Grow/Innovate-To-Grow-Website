import base64
import quopri
from email.message import EmailMessage
from email.policy import SMTP

from django.test import SimpleTestCase

from ...services.ingest.reading.parse import parse
from .. import corpus

SAVED = corpus.message(sender="Portal <noreply@i2g.example>", subject="Your sign-in link 登录", text="Your links: here")


def with_attached(body: bytes, encoding: str) -> bytes:
    """A message carrying ``body`` as a message/rfc822 part sent in ``encoding`` (RFC 2046 allows 7bit, 8bit, binary)."""
    head = (
        b"From: Sam <sam@example.org>\r\nContent-Type: multipart/mixed; boundary=b\r\n\r\n--b\r\n\r\nSee attached.\r\n"
    )
    part = f"--b\r\nContent-Type: message/rfc822\r\nContent-Transfer-Encoding: {encoding}\r\n\r\n".encode()
    return head + part + body + b"\r\n--b--\r\n"


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


class EncodedAttachedMessageTests(SimpleTestCase):
    """RFC 2046 forbids base64 and quoted-printable for message/rfc822, yet Python's email library writes base64 (and
    some clients do): the part is decoded and read like a forward, or counted as not readable."""

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
        headless = parse(with_attached(base64.encodebytes(b"Only some words, no headers.\r\n"), "base64"))

        self.assertEqual([item["subject"] for item in quoted.attached_messages], ["Your sign-in link 登录"])
        self.assertEqual((headless.attached_messages, headless.attached_dropped), ([], 1))
