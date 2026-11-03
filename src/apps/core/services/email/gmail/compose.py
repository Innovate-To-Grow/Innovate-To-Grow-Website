"""The MIME a Gmail API send uploads, and every site-side refusal, found before any token or network use."""

from apps.core.models.base.service_credentials.gmail_api import GmailApiProviderConfig, normalize_subject

from ..contracts import EmailMessage
from ..exceptions import PermanentEmailDeliveryError
from ..mime import build_mime_message, transport_bytes

# Headers that would name another sender than the impersonated account; no feature sets them.
_SENDER_HEADERS = ("sender", "return-path")
_RESENT_PREFIX = "resent-"
CREDENTIAL_MAIL_REFUSED = (
    "Gmail keeps a copy in Sent; mail with codes or login links is disabled for this provider "
    "(Gmail API config: Mail With Codes or Login Links)."
)


def encode(
    message: EmailMessage,
    *,
    from_email: str,
    from_name: str,
    subject: str,
    credential_mail: str,
    max_recipients: int,
    max_message_bytes: int,
) -> tuple[str, bytes]:
    """The MIME Message-ID and bytes. Every problem is definitive (Permanent)."""
    if normalize_subject(from_email) != subject:
        raise PermanentEmailDeliveryError("The Gmail API sends only From the account it impersonates.")
    if not message.keep_sent_copy and credential_mail == GmailApiProviderConfig.CredentialMail.REFUSE:
        raise PermanentEmailDeliveryError(CREDENTIAL_MAIL_REFUSED)
    if message.bcc:
        # build_mime_message never writes a Bcc header, and Google documents nothing about hiding one.
        raise PermanentEmailDeliveryError("The Gmail API provider does not support Bcc recipients.")
    for name in message.headers:
        folded = name.lower()
        if folded in _SENDER_HEADERS or folded.startswith(_RESENT_PREFIX):
            raise PermanentEmailDeliveryError(f"Email header {name!r} is not sent through the Gmail API.")
    if len(message.envelope_recipients) > max_recipients:
        raise PermanentEmailDeliveryError("The email has too many recipients for the Gmail API.")
    try:
        mime = build_mime_message(message, from_email=from_email, from_name=from_name)
        payload = transport_bytes(mime)
    except (ValueError, UnicodeError) as exc:
        raise PermanentEmailDeliveryError("The email could not be composed for the Gmail API.") from exc
    if len(payload) > max_message_bytes:
        raise PermanentEmailDeliveryError("The email is too large for the Gmail API.")
    return str(mime["Message-ID"]), payload
