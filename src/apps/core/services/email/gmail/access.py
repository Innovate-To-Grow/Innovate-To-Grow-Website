"""The site-side subject allow-list: which Google accounts the Gmail API service account may impersonate.

Domain-wide delegation lets the service account act as any user in the Workspace domain, and Google offers no
per-user restriction for it. Before any key read or token request, the subject must be on the active config's
allow-list, so a mistyped From address or a tampered value never reaches Google. This protects against site errors
only, not against someone who holds the key.
"""

from ..exceptions import PermanentEmailDeliveryError
from . import subject as subjects
from .auth import GmailCredential


class GmailScopeError(PermanentEmailDeliveryError):
    """The address is not on the configured Gmail API subject allow-list."""


def require_subject(config, address: str) -> subjects.AllowedSubject:
    """The checked subject for *address*; refuses, without contacting Google or the key store, when it is not listed."""
    if not config.allows(address):
        raise GmailScopeError(
            f"The Gmail API may not send as {address or 'an empty address'}: "
            "it is not on the configured subject allow-list."
        )
    return subjects.issue(address)


def credential_for(config) -> GmailCredential:
    """The key pointer and public facts of a ``GmailApiProviderConfig``. No store or Google call happens here."""
    if not config.key_configured:
        raise PermanentEmailDeliveryError("No Gmail API service-account key is installed.")
    return GmailCredential(
        service_account_email=config.service_account_email,
        client_id=config.client_id,
        key_id=config.key_id,
        key_ref=config.key_secret_ref,
        key_version_id=config.key_version_id,
    )
