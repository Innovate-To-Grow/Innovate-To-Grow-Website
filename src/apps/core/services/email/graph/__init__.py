"""Microsoft Graph (Outlook / Exchange Online) email provider and mailbox reader."""

from .identity.access import GraphScopeError
from .identity.auth import GraphCredential, clear_access_token_cache
from .provider import GraphProvider

__all__ = ["GraphCredential", "GraphProvider", "GraphScopeError", "clear_access_token_cache"]
