"""A requester's personal sign-in link never reaches staff, neither as a link nor in a file. In the HTML a removed
link is no link any more: its text stays, followed by the placeholder (as a relative href, the placeholder opened the
admin with "Ticket ... doesn't exist"). A saved message (``.eml``, whatever type it is sent as) is read like a
forwarded one and never kept as a file. A text file is stored with its sign-in links replaced and otherwise as it
came, in its own charset; binary files (PDF, Office, images, archives) are stored as received."""

import codecs
import hashlib
from email.message import EmailMessage
from email.policy import SMTP
from urllib.parse import quote

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.core.services.email.inbound import LINK_PLACEHOLDER as REMOVED

from ....models import HelpdeskSettings
from ....services.ingest.reading import attachments as files
from ....services.ingest.reading.message import ParsedAttachment
from ....services.ingest.reading.parse import parse
from ....services.ingest.reading.sanitize import sanitize_html
from ... import corpus
from ...helpers import helpdesk_staff, receive

LINK = corpus.LOGIN_LINK
TOKEN = LINK.split("token=")[1]
SAFE_LINK = f"https://nam02.safelinks.protection.outlook.com/?url={quote(LINK, safe='')}&amp;data=05%7C02"
DOC = "https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789/edit?usp=sharing"
EMAIL_SIGN_IN = "https://i2g.ucmerced.edu/email-auth-link#flow=login&amp;email=pat%40example.org&amp;code=123456"
SAVED = corpus.message(
    sender=f"Innovate to Grow <{corpus.SITE}>", subject="Your sign-in link", text=f"Sign in: {LINK}", message_id="<s@x>"
)


def html(markup: str) -> str:
    return sanitize_html(markup, max_chars=1024 * 1024)[0]


def mail_with(*attached, html_body=None) -> bytes:
    """A person's message carrying ``(file name, bytes, content type, Content-Type parameters)`` files."""
    mail = EmailMessage(policy=SMTP)
    mail["From"] = "Quinn Quote <quinn@example.org>"
    mail["To"] = corpus.SITE
    mail["Subject"] = "Fwd: the sign-in email I got"
    mail["Message-ID"] = "<files-1@example.org>"
    mail.set_content("The link in the attached files does not work for me.")
    if html_body:
        mail.add_alternative(html_body, subtype="html")
    for filename, data, content_type, params in attached:
        maintype, subtype = content_type.split("/")
        mail.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename, params=params)
    return mail.as_bytes()


class RemovedLinkTests(SimpleTestCase):
    def test_a_removed_link_is_its_text_and_the_placeholder_and_no_link(self):
        cleaned = html(
            f'<p><a href="{LINK}">Sign in to I2G</a>, <a href="{SAFE_LINK}"><b>Outlook</b></a>, '
            f'<a href="{DOC}">team document</a></p>'
        )

        self.assertEqual(
            cleaned,
            f"<p>Sign in to I2G {REMOVED}, <b>Outlook</b> {REMOVED}, "
            f'<a rel="noopener noreferrer" target="_blank" href="{DOC}">team document</a></p>',
        )

    def test_every_shape_of_a_removed_link_loses_its_anchor(self):
        cases = {
            f'<a href="{LINK}">{LINK}</a>': REMOVED,  # its text already shows the placeholder: once
            f'<a href="{corpus.UNSUBSCRIBE_LINK}"><img alt="Stop"></a>': f"[image: Stop] {REMOVED}",
            f'<a href="{LINK}"></a>': REMOVED,
            f'<a href="/login-link#token={TOKEN}">Sign in</a>': f"Sign in {REMOVED}",  # relative: it was kept whole
            f'<a href="mailto:pat@example.org?body={LINK}">mail it</a>': f"mail it {REMOVED}",
            '<a href="https://i2g.ucmerced.edu/login-link more">Sign in</a>': f"Sign in {REMOVED}",  # only scrubbing
            f'<a href="{EMAIL_SIGN_IN}">Sign in</a> {EMAIL_SIGN_IN}': f"Sign in {REMOVED} {REMOVED}",  # code mails
        }
        for markup, expected in cases.items():
            with self.subTest(markup):
                self.assertEqual(html(markup), expected)

    def test_a_cut_body_keeps_no_anchor_of_a_removed_link(self):
        paragraph = f'<p>See <a href="{LINK}">Sign in</a> here.</p>'

        cleaned, cut = sanitize_html(f"<div>{paragraph * 200}</div>", max_chars=2000)

        self.assertTrue(cut)
        self.assertNotIn("<a", cleaned)
        self.assertIn(f"<p>See Sign in {REMOVED} here.</p>", cleaned)


class SavedMessageTests(SimpleTestCase):
    def test_a_saved_message_is_read_like_a_forwarded_one_whatever_type_it_is_sent_as(self):
        for content_type in ("application/octet-stream", "text/plain", "application/x-eml"):
            with self.subTest(content_type):
                parsed = parse(mail_with(("I2G sign-in.EML", SAVED, content_type, None)))

                (attached,) = parsed.attached_messages
                self.assertEqual(
                    (attached["subject"], attached["text"].strip()), ("Your sign-in link", f"Sign in: {LINK}")
                )
                self.assertEqual(parsed.attachments, [])  # scrubbed when stored, never kept as a file

    def test_an_attachment_keeps_the_charset_it_was_sent_in(self):
        raw = mail_with(
            ("link.txt", b"x", "text/plain", {"charset": "windows-1252"}),
            ("a.bin", b"y", "application/octet-stream", None),
        )

        self.assertEqual([item.charset for item in parse(raw).attachments], ["windows-1252", ""])


def cp1252(link: str) -> bytes:
    """A Windows-1252 text file, ending in a byte that charset has no character for."""
    return f"Café € link: {link}\r\n".encode("cp1252") + b"\x81"


class TextFileTests(SimpleTestCase):
    def item(self, filename, data, content_type="application/octet-stream", charset=""):
        return ParsedAttachment(filename, content_type, data=data, size=len(data), charset=charset)

    def stored(self, *items) -> list[bytes]:
        return [row["content"] for row in files.prepare(list(items), HelpdeskSettings(), truncated=False)]

    def test_text_files_are_stored_without_sign_in_links_and_otherwise_as_they_came(self):
        text = f"Saved copy of the link: {LINK}\r\nThanks,\tQuinn\r\n"
        cleaned = text.replace(LINK, REMOVED).encode()
        for item in (
            self.item("link.txt", text.encode(), "text/plain"),
            self.item("links.CSV", text.encode(), "application/vnd.ms-excel"),
            self.item("event.ics", text.encode()),
            self.item("notes", text.encode(), "text/markdown"),
        ):
            with self.subTest(item.filename):
                self.assertEqual(self.stored(item), [cleaned])

    def test_binary_files_and_files_without_a_link_are_stored_as_they_came(self):
        unchanged = [
            self.item("report.txt", b"%PDF-1.7 /URI (" + LINK.encode() + b")", "text/plain"),  # a PDF by its content
            self.item("bundle.txt", b"PK\x03\x04" + LINK.encode()),
            self.item("data.bin", LINK.encode()),
            self.item("broken.txt", b"no link \xff\xfe\x00 here", "text/plain", "utf-8"),
        ]

        self.assertEqual(self.stored(*unchanged), [item.data for item in unchanged])

    def test_a_text_file_is_written_back_in_its_charset(self):
        def utf16(link: str, codec: str, mark: bytes = b"") -> bytes:
            return mark + f"link: {link}".encode(codec)

        cases = [
            (cp1252(LINK), "windows-1252", cp1252(REMOVED)),
            (utf16(LINK, "utf-16-le"), "utf-16-le", utf16(REMOVED, "utf-16-le")),
            (utf16(LINK, "utf-16-be", codecs.BOM_UTF16_BE), "", utf16(REMOVED, "utf-16-be", codecs.BOM_UTF16_BE)),
            (f"caf\u00e9 {LINK} done".encode(), "x-unknown", f"caf\u00e9 {REMOVED} done".encode()),
            (f"{LINK} done".encode(), "punycode", f"{REMOVED} done".encode()),  # codecs no mail client means
            (f"C:\\x41 {LINK}".encode(), "unicode_escape", f"C:\\x41 {REMOVED}".encode()),
        ]
        for data, charset, expected in cases:
            with self.subTest(charset or "byte order mark"):
                self.assertEqual(files.scrub_text_file(data, charset), expected)


class StoredFilesTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_neither_the_message_nor_its_files_hand_staff_a_sign_in_link(self):
        raw = mail_with(
            ("I2G sign-in.eml", SAVED, "application/octet-stream", None),
            ("link.txt", cp1252(LINK), "text/plain", {"charset": "windows-1252"}),
            html_body=f'<p>I clicked <a href="{LINK}">Sign in to I2G</a></p>',
        )

        ticket = receive(raw)

        message = ticket.messages.get()
        self.assertEqual(message.body_html, f"<p>I clicked Sign in to I2G {REMOVED}</p>")
        (attached,) = message.attached_messages
        self.assertEqual(attached["text"].strip(), f"Sign in: {REMOVED}")
        stored = message.attachments.get()  # the saved message is not a file
        content = bytes(stored.content)
        self.assertEqual((stored.filename, content), ("link.txt", cp1252(REMOVED)))
        self.assertEqual((stored.size, stored.sha256), (len(content), hashlib.sha256(content).hexdigest()))
        self.client.force_login(helpdesk_staff())
        download = self.client.get(reverse("admin:helpdesk_ticket_attachment", args=[ticket.pk, stored.pk]))
        self.assertEqual(download.content, content)
