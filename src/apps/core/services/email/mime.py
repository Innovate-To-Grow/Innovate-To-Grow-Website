"""MIME generation shared by all email providers."""

from email.message import EmailMessage as MimeMessage
from email.utils import formataddr, make_msgid

from .contracts import EmailMessage
from .exceptions import PermanentEmailDeliveryError

_PROTECTED_HEADERS = {"bcc", "cc", "from", "message-id", "reply-to", "subject", "to"}


def build_mime_message(message: EmailMessage, *, from_email: str, from_name: str = "") -> MimeMessage:
    """Build a standards-compliant MIME message without exposing Bcc."""
    if not message.envelope_recipients:
        raise PermanentEmailDeliveryError("Email has no recipients.")
    if not message.text_body and not message.html_body:
        raise PermanentEmailDeliveryError("Email has no body.")

    mime = MimeMessage()
    mime["Subject"] = message.subject
    mime["From"] = formataddr((from_name, from_email)) if from_name else from_email
    if message.to:
        mime["To"] = ", ".join(message.to)
    if message.cc:
        mime["Cc"] = ", ".join(message.cc)
    if message.reply_to:
        mime["Reply-To"] = ", ".join(message.reply_to)
    mime["Message-ID"] = make_msgid()

    for name, value in message.headers.items():
        if name.lower() in _PROTECTED_HEADERS:
            raise PermanentEmailDeliveryError(f"Email header {name!r} is managed by the delivery service.")
        mime[name] = value

    inline_attachments = [attachment for attachment in message.attachments if attachment.disposition == "inline"]
    ordinary_attachments = [attachment for attachment in message.attachments if attachment.disposition != "inline"]
    if inline_attachments and not message.html_body:
        raise PermanentEmailDeliveryError("Inline email attachments require an HTML body.")

    html_part = None
    if message.text_body:
        mime.set_content(message.text_body)
        if message.html_body:
            mime.add_alternative(message.html_body, subtype="html")
            html_part = mime.get_payload()[-1]
    else:
        mime.set_content(message.html_body or "", subtype="html")
        html_part = mime

    for attachment in inline_attachments:
        maintype, subtype = _attachment_content_type(attachment.content_type)
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

    for attachment in ordinary_attachments:
        maintype, subtype = _attachment_content_type(attachment.content_type)
        mime.add_attachment(
            attachment.content,
            maintype=maintype,
            subtype=subtype,
            filename=attachment.filename,
            disposition=attachment.disposition,
            cid=attachment.content_id,
        )
    return mime


def _attachment_content_type(content_type: str) -> tuple[str, str]:
    maintype, separator, subtype = content_type.partition("/")
    if not separator or not maintype or not subtype:
        raise PermanentEmailDeliveryError(f"Invalid attachment content type: {content_type!r}.")
    return maintype, subtype
