"""Provider-neutral email delivery contracts."""

from dataclasses import dataclass, field
from typing import Protocol

from apps.core.services.aws.provider_outcomes import PROVIDER_OUTCOME_SUCCESS


@dataclass(frozen=True)
class EmailAttachment:
    """A MIME attachment supplied as bytes."""

    filename: str
    content: bytes
    content_type: str = "application/octet-stream"
    disposition: str = "attachment"
    content_id: str | None = None


@dataclass(frozen=True)
class EmailMessage:
    """A complete outbound message independent of any delivery provider.

    ``keep_sent_copy=False`` marks a message that carries a credential (a sign-in code, a login link, an admin
    invitation, a ticket): a provider that would otherwise file a copy in the sender mailbox's Sent Items
    (Microsoft Graph) must not, because anyone who can read that folder could use it.
    """

    subject: str
    to: tuple[str, ...]
    text_body: str | None = None
    html_body: str | None = None
    cc: tuple[str, ...] = ()
    bcc: tuple[str, ...] = ()
    reply_to: tuple[str, ...] = ()
    attachments: tuple[EmailAttachment, ...] = ()
    headers: dict[str, str] = field(default_factory=dict)
    keep_sent_copy: bool = True

    @property
    def envelope_recipients(self) -> tuple[str, ...]:
        """Return all SMTP envelope recipients, preserving their order."""
        return tuple(dict.fromkeys((*self.to, *self.cc, *self.bcc)))


@dataclass(frozen=True)
class DeliveryResult:
    """A confirmed provider acceptance result."""

    provider: str
    message_id: str
    outcome: str = PROVIDER_OUTCOME_SUCCESS

    @property
    def accepted(self) -> bool:
        return self.outcome == PROVIDER_OUTCOME_SUCCESS


class EmailProvider(Protocol):
    """Contract implemented by concrete email delivery providers."""

    name: str

    def send(self, message: EmailMessage, *, before_provider_call=None) -> DeliveryResult:
        """Submit a message or raise a classified delivery exception.

        ``before_provider_call`` runs once every pre-submission step has succeeded and immediately before the
        message is handed to the provider; an exception it raises must propagate unclassified.
        """
        ...
