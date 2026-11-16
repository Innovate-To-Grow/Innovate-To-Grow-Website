"""MIME generation shared by all email providers."""

import email.policy
import re
from email.message import EmailMessage as MimeMessage
from email.utils import formataddr, make_msgid

from .contracts import EmailMessage
from .exceptions import PermanentEmailDeliveryError

# Marks a message that carries a credential (``keep_sent_copy=False``). Gmail files a copy of everything it sends in
# Sent (the Gmail API and Gmail SMTP alike), so the admin inbox and the Gmail import use this header to keep such
# copies out of what they list and cache.
MAIL_CLASS_HEADER = "X-I2G-Mail-Class"
CREDENTIAL_MAIL_CLASS = "credential"
# Headers the builders set themselves; a caller-supplied one is refused (JSON sendMail applies the same rule).
PROTECTED_HEADERS = {"bcc", "cc", "from", "message-id", "reply-to", "subject", "to", MAIL_CLASS_HEADER.lower()}
# RFC 5322 §2.2 field names: printable US-ASCII except the colon, so no space, tab or line break can slip a protected
# name past the check below (" X-I2G-Mail-Class" would otherwise fold into the previous header).
_FIELD_NAME_RE = re.compile(r"[!-9;-~]+")


def _set_headers(mime: MimeMessage, message: EmailMessage, *, from_email: str, from_name: str) -> None:
    mime["Subject"] = message.subject
    mime["From"] = formataddr((from_name, from_email)) if from_name else from_email
    for header, addresses in (("To", message.to), ("Cc", message.cc), ("Reply-To", message.reply_to)):
        if addresses:
            mime[header] = ", ".join(addresses)
    # Without a domain make_msgid() uses this host's FQDN, which would publish the server's internal name.
    mime["Message-ID"] = make_msgid(domain=from_email.rpartition("@")[2] or None)
    for name, value in message.headers.items():
        if not _FIELD_NAME_RE.fullmatch(str(name)):
            raise PermanentEmailDeliveryError("An email header is malformed.")
        if name.lower() in PROTECTED_HEADERS:
            raise PermanentEmailDeliveryError(f"Email header {name!r} is managed by the delivery service.")
        mime[name] = value
    if not message.keep_sent_copy:
        mime[MAIL_CLASS_HEADER] = CREDENTIAL_MAIL_CLASS


def _set_body(mime: MimeMessage, message: EmailMessage):
    """Set the text and/or HTML body; return the HTML part (where inline images attach), if any."""
    if not message.text_body:
        mime.set_content(message.html_body or "", subtype="html")
        return mime
    mime.set_content(message.text_body)
    if not message.html_body:
        return None
    mime.add_alternative(message.html_body, subtype="html")
    return mime.get_payload()[-1]


def _attach_inline(html_part, attachment) -> None:
    maintype, subtype = attachment_content_type(attachment.content_type)
    content_id = attachment.content_id or attachment.filename
    if not content_id.startswith("<"):
        content_id = f"<{content_id}>"
    html_part.add_related(
        attachment.content,
        maintype=maintype,
        subtype=subtype,
        filename=attachment.filename,
        disposition="inline",
        cid=content_id,
    )


def build_mime_message(message: EmailMessage, *, from_email: str, from_name: str = "") -> MimeMessage:
    """Build a standards-compliant MIME message without exposing Bcc."""
    if not message.envelope_recipients:
        raise PermanentEmailDeliveryError("Email has no recipients.")
    if not message.text_body and not message.html_body:
        raise PermanentEmailDeliveryError("Email has no body.")

    mime = MimeMessage()
    _set_headers(mime, message, from_email=from_email, from_name=from_name)

    inline_attachments = [attachment for attachment in message.attachments if attachment.disposition == "inline"]
    ordinary_attachments = [attachment for attachment in message.attachments if attachment.disposition != "inline"]
    if inline_attachments and not message.html_body:
        raise PermanentEmailDeliveryError("Inline email attachments require an HTML body.")

    html_part = _set_body(mime, message)
    for attachment in inline_attachments:
        _attach_inline(html_part, attachment)
    for attachment in ordinary_attachments:
        maintype, subtype = attachment_content_type(attachment.content_type)
        mime.add_attachment(
            attachment.content,
            maintype=maintype,
            subtype=subtype,
            filename=attachment.filename,
            disposition=attachment.disposition,
            cid=attachment.content_id,
        )
    return mime


def transport_bytes(mime: MimeMessage) -> bytes:
    """*mime* serialized for transmission: every line ends with CRLF, as RFC 5322 requires on the wire.

    ``as_bytes()`` with the default policy writes bare LF, which also makes every quoted-printable soft line
    break ``=LF``. Exchange Online (Microsoft Graph ``sendMail``) recognises a soft break only as ``=CRLF``: after
    a bare-LF one it keeps the ``=``, drops the LF and the next character, and so corrupts every long line of a
    campaign's HTML (``cellspacing=3D"0"``, ``font-weight:7=0``, a broken logo URL). CRLF decodes everywhere.
    """
    return mime.as_bytes(policy=email.policy.SMTP)


def attachment_content_type(content_type: str) -> tuple[str, str]:
    maintype, separator, subtype = content_type.partition("/")
    if not separator or not maintype or not subtype:
        raise PermanentEmailDeliveryError(f"Invalid attachment content type: {content_type!r}.")
    return maintype, subtype
