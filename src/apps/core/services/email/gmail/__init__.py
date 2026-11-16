"""Gmail API (Google Workspace) email provider: a service account with domain-wide delegation for gmail.send only.

Layers, each importing only the ones above it:

- ``service_account``: the key in the credential store (``stored_key``), the key file an admin pastes (``parsing``)
  and the RS256 JWT assertion it signs (``assertion``).
- ``client``: ``subject`` (the checked impersonation subject, a leaf) and ``access`` (the subject allow-list and the
  key pointer); ``auth`` (the token exchange and the per-process token cache); ``transport`` (the only two requests
  the site makes) and ``errors`` (Google's answers as classified errors); ``compose`` (the MIME and the site-side
  refusals) and ``provider`` (``messages.send``).
- ``key``: installing and removing the key; ``access_check``: what the admin's "Run access check" and
  ``verify_gmail_access`` prove.
"""

from .client.access import GmailScopeError
from .client.auth import GmailCredential, clear_access_token_cache
from .client.provider import GmailProvider

__all__ = ["GmailCredential", "GmailProvider", "GmailScopeError", "clear_access_token_cache"]
