"""
Custom throttle classes for auth endpoints.
"""

from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class ContactEmailCreateThrottle(UserRateThrottle):
    """Throttle for adding contact emails: 5 requests per hour."""

    scope = "contact_email_create"


class LoginRateThrottle(AnonRateThrottle):
    """Throttle for login endpoints: 10 requests per minute."""

    scope = "login"


class EmailCodeRequestThrottle(AnonRateThrottle):
    """Throttle for verification code request endpoints."""

    scope = "email_code_request"


class EmailCodeVerifyThrottle(AnonRateThrottle):
    """Throttle for verification code and token confirmation endpoints."""

    scope = "email_code_verify"
