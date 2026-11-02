"""Gmail API (Google Workspace) email provider: a service account with domain-wide delegation for gmail.send only.

- ``subject``: the checked impersonation subject (a leaf); ``access``: the subject allow-list and the key pointer.
- ``assertion``: the RS256 JWT assertion; ``auth``: the token exchange and the per-process token cache.
- ``transport``: the only two requests the site makes; ``errors``: Google's answers as classified errors.
- ``compose``: the MIME and the site-side refusals; ``provider``: ``messages.send``; ``key``: the service-account
  key (store, parsing, install, removal);
  ``access_check``: what the admin's "Run access check" and ``verify_gmail_access`` prove.
"""

from .access import GmailScopeError
from .auth import GmailCredential, clear_access_token_cache
from .provider import GmailProvider

__all__ = ["GmailCredential", "GmailProvider", "GmailScopeError", "clear_access_token_cache"]
