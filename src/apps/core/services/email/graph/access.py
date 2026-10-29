"""The site-side mailbox scope: which mailboxes the Graph app may use, and with which permission.

Every Graph request names one mailbox in its URL. Before any request is made, the mailbox must be listed in the
active config's mailbox scope with the permission the request needs, so a mistyped sender or a tampered value can
never reach a mailbox outside the scope even if the tenant-side restriction were missing or misconfigured.
"""

from ..exceptions import PermanentEmailDeliveryError
from .auth import GraphCredential

SEND = "send"
READ = "read"


class GraphScopeError(PermanentEmailDeliveryError):
    """The mailbox is outside the configured Microsoft Graph mailbox scope for this permission."""


def credential_for(config) -> GraphCredential:
    """The Entra credential of a ``MicrosoftGraphProviderConfig`` for its selected authentication method."""
    if config.uses_certificate:
        return GraphCredential(
            tenant_id=config.tenant_id,
            client_id=config.client_id,
            private_key_pem=config.private_key,
            certificate_thumbprint=config.certificate_thumbprint,
        )
    return GraphCredential(tenant_id=config.tenant_id, client_id=config.client_id, client_secret=config.client_secret)


def require_mailbox(config, mailbox: str, permission: str) -> str:
    """Return *mailbox* when the scope grants *permission* on it; otherwise refuse without contacting Microsoft."""
    if not config.allows(mailbox, permission):
        verb = "send as" if permission == SEND else "read"
        raise GraphScopeError(
            f"Microsoft Graph may not {verb} {mailbox or 'an empty mailbox'}: "
            "it is not in the configured mailbox scope with that permission."
        )
    return mailbox
