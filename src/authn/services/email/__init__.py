"""Email-related auth service modules."""

from .auth_email import (
    ResolvedAuthEmail,
    get_member_auth_emails,
    normalize_email,
    registration_email_conflicts,
    resolve_auth_email,
)
from .auth_mail import AuthEmailError, send_auth_code_email
from .invitation_mail import InvitationEmailError, send_admin_invitation_email

__all__ = [
    "ResolvedAuthEmail",
    "get_member_auth_emails",
    "normalize_email",
    "registration_email_conflicts",
    "resolve_auth_email",
    "AuthEmailError",
    "send_auth_code_email",
    "InvitationEmailError",
    "send_admin_invitation_email",
]
