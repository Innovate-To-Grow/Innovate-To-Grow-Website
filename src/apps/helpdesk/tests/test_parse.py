"""Reading raw MIME into a message: envelope, bodies, attachments, attached messages, and hostile or cut-off input."""

import base64
from datetime import UTC, datetime

from django.test import SimpleTestCase

from ..services.ingest import parse as parsing
from ..services.ingest.parse import clean_filename, parse
from . import corpus


class EnvelopeTests(SimpleTestCase):
    def test_reads_the_envelope_headers(self):
        raw = corpus.message(
            sender="=?utf-8?q?Jos=C3=A9_Ruiz?= <Jose.Ruiz@Example.org>",
            cc="Kim <kim@example.org>, bad-address",
            subject="=?utf-8?q?Caf=C3=A9_question?=",
            in_reply_to="<parent@example.org>",
            references="<root@example.org> <parent@example.org>",
            headers={"Reply-To": "Help Desk <desk@example.org>"},
        )

        parsed = parse(raw)

        self.assertEqual((parsed.from_name, parsed.from_address), ("José Ruiz", "jose.ruiz@example.org"))
        self.assertEqual(
            (parsed.to, parsed.cc, parsed.reply_to), (["i2g@ucmerced.edu"], ["kim@example.org"], "desk@example.org")
        )
        self.assertEqual(parsed.subject, "Café question")
        self.assertEqual(parsed.message_id, "<m1@mail.example.org>")
        self.assertEqual(parsed.in_reply_to, "<parent@example.org>")
        self.assertEqual(parsed.references, ["<root@example.org>", "<parent@example.org>"])
        self.assertEqual(parsed.sent_at, datetime(2026, 11, 11, 10, 0, tzinfo=UTC))
        self.assertEqual((parsed.content_type, parsed.truncated, parsed.incomplete), ("text/plain", False, False))

    def test_a_message_without_a_message_id_is_fingerprinted_by_its_content(self):
        first = parse(corpus.message(message_id=None))
        same = parse(corpus.message(message_id=None))
        other = parse(corpus.message(message_id=None, text="Something else"))

        self.assertEqual(first.message_id, "")
        self.assertEqual(first.fingerprint(), same.fingerprint())
        self.assertNotEqual(first.fingerprint(), other.fingerprint())
        self.assertNotEqual(first.fingerprint(), parse(corpus.message()).fingerprint())


class BodyTests(SimpleTestCase):
    def test_text_and_html_alternatives(self):
        parsed = parse(corpus.message(text="Plain\r\nlines", html="<p>Rich</p>"))

        self.assertEqual(parsed.text.strip(), "Plain\nlines")
        self.assertIn("<p>Rich</p>", parsed.html)
        self.assertEqual(parsed.text_head(), parsed.text)

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


class AttachmentTests(SimpleTestCase):
    def test_attachments_with_their_bytes(self):
        raw = corpus.message(attachments=[("report.pdf", b"%PDF-1.7 data", "application/pdf")])

        (item,) = parse(raw).attachments

        self.assertEqual(
            (item.filename, item.content_type, item.data, item.size),
            ("report.pdf", "application/pdf", b"%PDF-1.7 data", 13),
        )
        self.assertFalse(item.is_inline)

    def test_inline_parts_with_a_content_id(self):
        raw = (
            b"From: a@example.org\r\nContent-Type: multipart/related; boundary=b\r\n\r\n--b\r\n"
            b"Content-Type: text/html\r\n\r\n<img src=cid:logo>\r\n--b\r\nContent-Type: image/png\r\n"
            b"Content-ID: <logo>\r\nContent-Transfer-Encoding: base64\r\n\r\niVBORw0KGgo=\r\n--b--\r\n"
        )

        (item,) = parse(raw).attachments

        self.assertEqual((item.content_id, item.is_inline, item.content_type), ("<logo>", True, "image/png"))
        self.assertTrue(item.filename.endswith(".png"))

    def test_file_names_lose_directories_and_control_characters(self):
        self.assertEqual(clean_filename("..\\..\\windows\\evil.exe"), "evil.exe")
        self.assertEqual(clean_filename("/etc/passwd\x00"), "passwd")
        self.assertEqual(clean_filename(".hidden"), "hidden")
        long_name = clean_filename("a" * 400 + ".pdf")
        self.assertEqual((len(long_name) <= 255, long_name.endswith(".pdf")), (True, True))
        self.assertEqual(len(clean_filename("b" * 400)), 255)

    def test_file_names_lose_the_trailing_dots_and_spaces_windows_would_drop(self):
        # Saved by Windows as "evil.js" and "evil.hta": the blocked-type check must see that extension.
        self.assertEqual(clean_filename("evil.js."), "evil.js")
        self.assertEqual(clean_filename("evil.hta . ."), "evil.hta")
        self.assertEqual(clean_filename(" . "), "")
        cut = clean_filename("x" * 251 + ".js." + "c" * 20)  # cut inside a long last part: no dot left at the end
        self.assertEqual((len(cut), cut.endswith(".js")), (254, True))


class AttachedMessageTests(SimpleTestCase):
    def test_a_forwarded_message_is_summarized_never_kept_raw(self):
        parsed = parse(corpus.forwarded())

        (attached,) = parsed.attached_messages
        self.assertEqual(attached["subject"], "Your ticket")
        self.assertIn("i2g@ucmerced.edu", attached["from"])
        self.assertIn(corpus.LOGIN_LINK, attached["text"])  # scrubbed when stored, not when parsed
        self.assertEqual(parsed.attachments, [])

    def test_a_bounce_reports_returned_message_is_summarized(self):
        parsed = parse(corpus.bounce_report())

        self.assertEqual((parsed.content_type, parsed.report_type), ("multipart/report", "delivery-status"))
        self.assertIn("couldn't be delivered", parsed.text)


class HostileInputTests(SimpleTestCase):
    def test_a_cut_off_message_keeps_what_was_read(self):
        raw = corpus.message(text="Long body " * 50, attachments=[("a.pdf", b"%PDF-" + b"x" * 5000, "application/pdf")])

        parsed = parse(raw[: len(raw) // 2], truncated=True)

        self.assertTrue(parsed.truncated)
        self.assertIn("Long body", parsed.text)

    def test_too_many_parts_or_levels_mark_the_message_incomplete(self):
        boundary_open = "".join(
            f'Content-Type: multipart/mixed; boundary="b{index}"\r\n\r\n--b{index}\r\n' for index in range(20)
        )
        deep = f"From: a@example.org\r\n{boundary_open}Content-Type: text/plain\r\n\r\ndeep\r\n".encode()

        self.assertTrue(parse(deep).incomplete)

        parts = "".join("--b\r\nContent-Type: text/plain\r\n\r\npart\r\n" for _ in range(parsing.MAX_PARTS + 5))
        wide = f"From: a@example.org\r\nContent-Type: multipart/mixed; boundary=b\r\n\r\n{parts}--b--\r\n".encode()
        parsed = parse(wide)
        self.assertTrue(parsed.incomplete)
        self.assertLessEqual(parsed.text.count("part"), parsing.MAX_PARTS)

    def test_malformed_mime_does_not_raise(self):
        for raw in (
            b"",
            b"\xff\xfe\x00garbage",
            b"Content-Type: multipart/mixed\r\n\r\nno boundary at all",
            b"Content-Type: multipart/mixed; boundary=x\r\n\r\n--x\r\nContent-Transfer-Encoding: base64\r\n\r\n!!!\r\n--x",
            b"Content-Type: message/rfc822\r\n\r\n",
        ):
            with self.subTest(raw=raw[:30]):
                parsed = parse(raw)
                self.assertIsInstance(parsed.text, str)


class BrokenPart:
    """A MIME part whose every accessor fails, as a hostile structure can make them."""

    def __getattr__(self, name):
        def fail(*args, **kwargs):
            raise ValueError(name)

        return fail


class PartErrorTests(SimpleTestCase):
    def test_a_part_that_cannot_be_read_is_skipped_safely(self):
        part = BrokenPart()

        self.assertEqual(parsing._content_type(part), "application/octet-stream")
        self.assertEqual(parsing._disposition(part), "")
        self.assertEqual(parsing._filename(part), "")
        self.assertEqual(parsing._decode_text(part), "")

    def test_an_attachment_that_cannot_be_decoded_keeps_its_name(self):
        walker = parsing._Walker(parsing.ParsedMessage(headers={}))
        part = BrokenPart()
        part.get = lambda name: None

        walker._attachment(part, "application/pdf", "attachment", "report.pdf")

        (item,) = walker.parsed.attachments
        self.assertEqual((item.filename, item.data, item.size), ("report.pdf", None, 0))

    def test_a_charset_python_does_not_know_falls_back_to_utf8(self):
        class Part:
            def get_payload(self, decode=False):
                return "café".encode()

            def get_content_charset(self):
                return "no-such-charset"

        self.assertEqual(parsing._decode_text(Part()), "café")
        self.assertEqual(parsing._header(type("P", (), {"get": lambda self, name: None})(), "Content-ID"), "")
