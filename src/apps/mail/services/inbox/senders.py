"""The addresses an Inbox reply may be sent From, across every configured email account.

* ``default``: Mail -> Notification Delivery (the active ``EmailServiceConfig``: its provider and From address).
* ``graph:<address>``: a mailbox of the active Microsoft Graph configuration whose scope lets it send, once that
  configuration has passed what switching email to Graph requires (``takeover_problem``).
* ``gmail_api:<address>``: a Workspace account on the active Gmail API allow-list, verified by its access check
  (``activation_problem``).
* ``imap:<row id>``: a Gmail IMAP access account that allows replies, over SMTP with its own login.

A reply names its sender by ``key``; only a key listed here is honoured, and each provider re-checks its allow-list
when the message is sent (``core.services.email.sending.registry``), so a hand-written key or an account removed
meanwhile never sends. An address offered by several accounts is listed once, from the first of them above.
"""

import logging
from dataclasses import dataclass
from types import SimpleNamespace

from django.db.utils import OperationalError, ProgrammingError

from apps.core.models import (
    EmailServiceConfig,
    GmailAccessAccount,
    GmailApiProviderConfig,
    MicrosoftGraphProviderConfig,
)
from apps.core.models.base.service_credentials.microsoft_graph.access_check import takeover_problem
from apps.core.utils.security import is_plain_address

logger = logging.getLogger(__name__)

DEFAULT_SENDER = "default"


@dataclass(frozen=True)
class SendIdentity:
    """One From address a reply may use, and how it is sent."""

    key: str
    address: str
    provider: str
    via: str
    gmail_account_id: int | None = None

    @property
    def label(self) -> str:
        return f"{self.address} ({self.via})"

    def delivery_config(self, base: EmailServiceConfig):
        """The configuration ``deliver_email`` sends this reply with: the active one for ``default``, else a
        stand-in naming this provider and address (the provider factory re-checks it)."""
        if self.key == DEFAULT_SENDER:
            return base
        return SimpleNamespace(
            provider=self.provider,
            from_email=self.address,
            from_name=base.from_name,
            is_active=True,
            gmail_account_id=self.gmail_account_id,
        )


def send_identities() -> list[SendIdentity]:
    """Every address a reply may be sent From, Notification Delivery's first. Empty when none can send."""
    identities: list[SendIdentity] = []
    for source in (_default_identity, _graph_identities, _gmail_api_identities, _imap_identities):
        try:
            found = source()
        except (OperationalError, ProgrammingError):
            raise
        except Exception:
            # One provider's broken configuration must not hide the other From choices.
            logger.exception("Could not list the reply senders of %s.", source.__name__)
            continue
        identities.extend(found)
    return _unique(identities)


def resolve_identity(key: str | None) -> SendIdentity | None:
    """The sender *key* names (None or "": ``default``), or None when it is not a current choice."""
    key = key or DEFAULT_SENDER
    return next((identity for identity in send_identities() if identity.key == key), None)


def default_identity_for(identities: list[SendIdentity], address: str) -> SendIdentity | None:
    """The From choice a reply starts with: the address the message was received at when the site can send as it,
    else Notification Delivery's (the first choice)."""
    wanted = str(address or "").strip().lower()
    for identity in identities:
        if identity.address.lower() == wanted:
            return identity
    return identities[0] if identities else None


def _default_identity() -> list[SendIdentity]:
    config = EmailServiceConfig.load()
    if not config.is_active or not config.delivery_configured or not is_plain_address(config.from_email):
        return []
    via = f"Notification Delivery · {config.get_provider_display()}"
    return [SendIdentity(DEFAULT_SENDER, config.from_email.strip(), config.provider, via)]


def _graph_identities() -> list[SendIdentity]:
    graph = MicrosoftGraphProviderConfig.load()
    if not graph.is_configured or takeover_problem(graph):
        return []
    return [
        SendIdentity(f"graph:{scope.mailbox}", scope.mailbox, EmailServiceConfig.Provider.GRAPH, "Microsoft Graph")
        for scope in graph.mailbox_scopes.all()
        if scope.grants("send") and is_plain_address(scope.mailbox) and graph.sending_ready(scope.mailbox)
    ]


def _gmail_api_identities() -> list[SendIdentity]:
    gmail = GmailApiProviderConfig.load()
    if not gmail.is_configured:
        return []
    return [
        SendIdentity(f"gmail_api:{subject.subject}", subject.subject, EmailServiceConfig.Provider.GMAIL, "Gmail API")
        for subject in gmail.subjects.all()
        if not gmail.activation_problem(subject.subject)
    ]


def _imap_identities() -> list[SendIdentity]:
    return [
        SendIdentity(f"imap:{row.pk}", row.gmail_username.strip(), "gmail_smtp", f"SMTP · {row.smtp_host}", row.pk)
        for row in GmailAccessAccount.objects.filter(reply_enabled=True).order_by("-is_active", "gmail_username", "pk")
        if row.reply_configured and is_plain_address(row.gmail_username.strip())
    ]


def _unique(identities: list[SendIdentity]) -> list[SendIdentity]:
    seen, unique = set(), []
    for identity in identities:
        address = identity.address.lower()
        if address not in seen:
            seen.add(address)
            unique.append(identity)
    return unique
