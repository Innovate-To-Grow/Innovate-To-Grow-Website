from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class CliOAuthThrottle(AnonRateThrottle):
    """Per-IP throttle for the unauthenticated token-exchange endpoint."""

    scope = "cli_oauth"


class CliReadThrottle(UserRateThrottle):
    """Per-member throttle for read operations."""

    scope = "cli_read"


class CliWriteThrottle(UserRateThrottle):
    """Per-member throttle for write operations."""

    scope = "cli_write"
