"""Patch-compatible authentication email sending namespace."""

from .actions import render_email_body as _render_email_body
from .senders import (
    send_admin_invitation_email,
    send_notification_email,
    send_verification_email,
)
from .transport import _load_config, _send_via_ses

__all__ = [
    "send_admin_invitation_email",
    "send_notification_email",
    "send_verification_email",
]
