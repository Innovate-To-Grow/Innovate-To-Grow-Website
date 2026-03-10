"""
Custom throttle classes for auth endpoints.
"""

from rest_framework.throttling import AnonRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    """Throttle for login endpoints: 10 requests per minute."""

    scope = "login"


class EmailCodeRequestThrottle(AnonRateThrottle):
    """Throttle for verification code request endpoints."""

    scope = "email_code_request"


class EmailCodeVerifyThrottle(AnonRateThrottle):
    """Throttle for verification code and token confirmation endpoints."""

    scope = "email_code_verify"
