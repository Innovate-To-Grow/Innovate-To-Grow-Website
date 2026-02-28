"""
Custom throttle classes for auth endpoints.
"""

from rest_framework.throttling import AnonRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    """Throttle for login endpoints: 10 requests per minute."""

    scope = "login"


class VerifyRateThrottle(AnonRateThrottle):
    """Throttle for verification endpoints: 10 requests per minute."""

    scope = "verify"
