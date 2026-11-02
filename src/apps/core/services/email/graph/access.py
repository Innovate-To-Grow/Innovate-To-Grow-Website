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
    """The certificate credential of a ``MicrosoftGraphProviderConfig``: its current certificate's pinned key.

    No store or Entra call happens here. A config without a usable current certificate (none installed, removed,
    expired, not valid yet, or tested for another app) is refused.
    """
    certificate = config.current_certificate
    if certificate is None or not certificate.usable_for(config):
        raise PermanentEmailDeliveryError("No usable Microsoft Graph certificate is installed.")
    return GraphCredential(
        tenant_id=config.tenant_id,
        client_id=config.client_id,
        x5t_s256=certificate.x5t_s256,
        public_key_sha256=certificate.public_key_sha256,
        key_arn=certificate.store_arn,
        key_version_id=certificate.store_version_id,
    )


def require_mailbox(config, mailbox: str, permission: str) -> str:
    """Return *mailbox* when the scope grants *permission* on it; otherwise refuse without contacting Microsoft."""
    if not config.allows(mailbox, permission):
        verb = "send as" if permission == SEND else "read"
        raise GraphScopeError(
            f"Microsoft Graph may not {verb} {mailbox or 'an empty mailbox'}: "
            "it is not in the configured mailbox scope with that permission."
        )
    return mailbox
