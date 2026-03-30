"""Email-related auth service modules."""

from .auth_email import (
    ResolvedAuthEmail,
    get_member_auth_emails,
    normalize_email,
    registration_email_conflicts,
    resolve_auth_email,
)
from .send_email import send_verification_email

__all__ = [
    "ResolvedAuthEmail",
    "get_member_auth_emails",
    "normalize_email",
    "registration_email_conflicts",
    "resolve_auth_email",
    "send_verification_email",
]
