"""Parsing raw MIME into the tree of parts the walker reads: ``compat32``, as core's ``headers.parse``, except that an
attached message sent base64 or quoted-printable is kept as its encoded text, to be decoded and read on its own like a
saved .eml file.

RFC 2046 forbids encoding message/rfc822, yet Python's email library writes base64 (and quoted-printable when asked),
and message/global may be encoded. Python's parser reads the text of any message part as a message, encoded or not:
in quoted-printable, a soft line break ("=" at the end of a line, at most 76 characters apart) ends a header inside its
value, the real headers land in the body, and the body's own encoding is never undone, so tokens stay readable across
the breaks. Nor can the encoded text be rebuilt exactly from what the parser kept (reading headers, it drops a line
that starts with ":"), so it is kept as it came.
"""

import email
import email.message
import email.policy

from .message import NESTED_TYPES

ENCODINGS = frozenset({"base64", "quoted-printable"})


class _Part(email.message.Message):
    def get_content_maintype(self) -> str:
        """What the parser asks to read a part's text as a message ("message"): an encoded attached message says
        "application", so its text is kept as it came."""
        if self.get_content_type() in NESTED_TYPES and _encoding(self) in ENCODINGS:
            return "application"
        return super().get_content_maintype()


def _encoding(part) -> str:
    return str(part.get("Content-Transfer-Encoding", ""))[:64].strip().lower()


def parse_mime(raw: bytes):
    """The tree of MIME parts in ``raw`` (``compat32``: nothing is decoded until it is read)."""
    return email.message_from_bytes(raw, _class=_Part, policy=email.policy.compat32)
