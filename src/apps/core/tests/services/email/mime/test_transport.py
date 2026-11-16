"""The bytes a provider transmits: CRLF line endings throughout, including quoted-printable soft line breaks.

Exchange Online (Microsoft Graph ``sendMail``) decodes a soft break only at ``=CRLF``; a bare-LF one left the
``=`` in the text and dropped the next character, so every long HTML line of a campaign arrived corrupted."""

import email
import email.policy
import quopri

from django.test import SimpleTestCase

from apps.core.services.email import EmailMessage
from apps.core.services.email.mime import build_mime_message, transport_bytes

# One line far longer than the 76 characters a quoted-printable line may hold, as every campaign has.
LONG_LINE = '<td style="height:4px;background-color:#daa520;border-radius:4px 4px 0 0;' + "x" * 120 + '"></td>'
HTML = f'<p>Innovate to Grow caf\N{LATIN SMALL LETTER E WITH ACUTE}</p>\n{LONG_LINE}\n<p>cellspacing="0"</p>\n'


def build(**values):
    message = EmailMessage(subject="Hello", to=("to@example.com",), **values)
    return build_mime_message(message, from_email="from@example.com", from_name="Innovate to Grow")


def lf(text: str) -> str:
    """Decoded content keeps the wire's CRLF hard line breaks; compare it against the source with LF."""
    return text.replace("\r\n", "\n")


def strict_crlf_decode(data: bytes) -> bytes:
    """Decode quoted-printable the way a CRLF-only decoder does: ``=CRLF`` is a soft break, ``=XY`` a byte, and
    any other ``=`` keeps the ``=`` and skips the next two characters (what the corrupted copies showed)."""
    out, index = bytearray(), 0
    while index < len(data):
        byte = data[index : index + 1]
        if byte != b"=":
            out += byte
            index += 1
        elif data[index + 1 : index + 3] == b"\r\n":
            index += 3
        else:
            try:
                out.append(int(data[index + 1 : index + 3], 16))
            except ValueError:
                out += b"="
            index += 3
    return bytes(out)


class TransportBytesTests(SimpleTestCase):
    def test_every_line_ends_with_crlf(self):
        raw = transport_bytes(build(html_body=HTML))

        self.assertIn(b"\r\n", raw)
        self.assertEqual(raw.count(b"\n"), raw.count(b"\r\n"), "a bare LF remains")
        self.assertNotIn(b"\r\r\n", raw)

    def test_quoted_printable_soft_breaks_are_crlf_and_decode_strictly(self):
        mime = build(html_body=HTML)
        raw = transport_bytes(mime)
        body = raw.split(b"\r\n\r\n", 1)[1]

        self.assertEqual(mime["Content-Transfer-Encoding"], "quoted-printable")
        self.assertIn(b"=\r\n", body)
        self.assertEqual(lf(strict_crlf_decode(body).decode("utf-8")), HTML)
        self.assertEqual(lf(quopri.decodestring(body).decode("utf-8")), HTML)

    def test_default_serialization_is_what_the_strict_decoder_corrupts(self):
        # Documents why transport_bytes exists: the default policy's bare-LF soft breaks lose characters.
        body = build(html_body=HTML).as_bytes().split(b"\n\n", 1)[1]

        self.assertIn(b"=\n", body)
        self.assertNotEqual(strict_crlf_decode(body).decode("utf-8", "replace"), HTML)

    def test_parses_back_to_the_same_message(self):
        raw = transport_bytes(build(text_body="Plain", html_body=HTML, headers={"List-Unsubscribe": "<https://u>"}))

        parsed = email.message_from_bytes(raw, policy=email.policy.default)
        self.assertEqual(parsed["Subject"], "Hello")
        self.assertEqual(parsed["List-Unsubscribe"], "<https://u>")
        self.assertEqual(lf(parsed.get_body(preferencelist=("html",)).get_content()), HTML)
        self.assertEqual(lf(parsed.get_body(preferencelist=("plain",)).get_content()), "Plain\n")
