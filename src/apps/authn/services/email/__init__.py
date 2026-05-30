"""Email-related auth service modules."""

from .auth_email import (
    ResolvedAuthEmail,
    claim_unclaimed_contact_email,
    get_member_auth_emails,
    get_pending_registration_member,
    normalize_email,
    registration_email_conflicts,
    resolve_auth_email,
)
from .send_email import send_admin_invitation_email, send_notification_email, send_verification_email

__all__ = [
    "ResolvedAuthEmail",
    "claim_unclaimed_contact_email",
    "get_member_auth_emails",
    "get_pending_registration_member",
    "normalize_email",
    "registration_email_conflicts",
    "resolve_auth_email",
    "send_admin_invitation_email",
    "send_notification_email",
    "send_verification_email",
]
