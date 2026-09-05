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
    """A complete outbound message independent of any delivery provider."""

    subject: str
    to: tuple[str, ...]
    text_body: str | None = None
    html_body: str | None = None
    cc: tuple[str, ...] = ()
    bcc: tuple[str, ...] = ()
    reply_to: tuple[str, ...] = ()
    attachments: tuple[EmailAttachment, ...] = ()
    headers: dict[str, str] = field(default_factory=dict)

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

    def send(self, message: EmailMessage) -> DeliveryResult:
        """Submit a message or raise a classified delivery exception."""
        ...
