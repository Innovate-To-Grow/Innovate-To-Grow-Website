"""Per-member throttles for the authenticated CLI endpoints.

The token-exchange endpoint (``OAuthTokenView``) deliberately has no throttle. A per-IP bucket there only limited
staff sharing the campus public IP, and it protected nothing: the authorization code is a 384-bit single-use secret
that lives 60 seconds, is burned by the first attempt (even a failed one) and is bound to the PKCE verifier and the
exact redirect URI. Do not add an anonymous (per-IP) throttle here.
"""

from rest_framework.throttling import UserRateThrottle


class CliReadThrottle(UserRateThrottle):
    """Per-member throttle for read operations."""

    scope = "cli_read"


class CliWriteThrottle(UserRateThrottle):
    """Per-member throttle for write operations."""

    scope = "cli_write"
