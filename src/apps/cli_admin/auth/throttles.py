"""Per-member throttles for the authenticated CLI endpoints.

The token-exchange endpoint (``OAuthTokenView``) deliberately has no throttle. A per-IP bucket there only limited
staff sharing the campus public IP, and it protected nothing: the authorization code is a 384-bit single-use secret
that lives 60 seconds, is burned by the first attempt (even a failed one) and is bound to the PKCE verifier and the
exact redirect URI. Do not add an anonymous (per-IP) throttle here.
"""

from apps.core.services.request_limits.view_limits import MemberRateThrottle


class CliReadThrottle(MemberRateThrottle):
    """Per-member throttle for read operations (a live request-limit policy)."""

    scope = "cli_read"
    policy_scope = "view-cli-read"


class CliWriteThrottle(MemberRateThrottle):
    """Per-member throttle for write operations (a live request-limit policy)."""

    scope = "cli_write"
    policy_scope = "view-cli-write"
