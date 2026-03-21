"""
Signed auto-login tokens for email unsubscribe / preference management.

Follows the same pattern as event/services/ticket_assets.py.
"""

from django.core import signing

from event.services.ticket_assets import build_frontend_absolute_url

_UNSUBSCRIBE_LOGIN_SALT = "email-unsubscribe-login"
_UNSUBSCRIBE_LOGIN_MAX_AGE = 60 * 60 * 24 * 7  # 7 days


def build_unsubscribe_login_token(member) -> str:
    """Create a signed token that allows one-click login for email preference management."""
    return signing.dumps({"member_id": str(member.pk)}, salt=_UNSUBSCRIBE_LOGIN_SALT, compress=True)


def get_member_from_unsubscribe_token(token: str):
    """Validate an unsubscribe login token and return the associated Member."""
    from authn.models import Member

    try:
        payload = signing.loads(token, salt=_UNSUBSCRIBE_LOGIN_SALT, max_age=_UNSUBSCRIBE_LOGIN_MAX_AGE)
        member_id = payload["member_id"]
    except signing.BadSignature as exc:
        raise ValueError("Invalid or expired login link.") from exc

    try:
        return Member.objects.get(pk=member_id, is_active=True)
    except Member.DoesNotExist as exc:
        raise ValueError("Account not found.") from exc


def build_unsubscribe_url(member) -> str:
    """Build the full frontend URL for the unsubscribe auto-login page."""
    token = build_unsubscribe_login_token(member)
    return build_frontend_absolute_url(f"/unsubscribe-login?token={token}")
