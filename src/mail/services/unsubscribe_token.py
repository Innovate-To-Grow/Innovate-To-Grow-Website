"""RFC 8058 one-click unsubscribe token utilities."""

import logging

from django.conf import settings
from django.core import signing

logger = logging.getLogger(__name__)

_SALT = "rfc8058-one-click-unsubscribe"
_MAX_AGE = 60 * 60 * 24 * 90  # 90 days


def build_oneclick_unsubscribe_token(member_or_id) -> str:
    """Create a signed token encoding the member's PK.

    Accepts a Member instance or a raw UUID/string PK.
    """
    pk = str(member_or_id.pk if hasattr(member_or_id, "pk") else member_or_id)
    return signing.dumps({"member_id": pk}, salt=_SALT, compress=True)


def get_member_from_oneclick_token(token: str):
    """Validate a one-click unsubscribe token and return the Member.

    Raises ``ValueError`` on invalid, expired, or unknown-member tokens.
    """
    from authn.models import Member

    try:
        payload = signing.loads(token, salt=_SALT, max_age=_MAX_AGE)
        member_id = payload["member_id"]
    except (signing.BadSignature, KeyError) as exc:
        raise ValueError("Invalid or expired unsubscribe link.") from exc

    try:
        return Member.objects.get(pk=member_id, is_active=True)
    except Member.DoesNotExist as exc:
        raise ValueError("Account not found.") from exc


def build_oneclick_unsubscribe_url(member_or_id) -> str:
    """Return the absolute backend URL for the one-click unsubscribe endpoint.

    Accepts a Member instance or a raw UUID/string PK.
    Returns empty string when ``BACKEND_URL`` is not configured (header
    injection will be skipped).
    """
    backend_url = (getattr(settings, "BACKEND_URL", "") or "").strip().rstrip("/")
    if not backend_url:
        logger.warning("BACKEND_URL is not configured; skipping one-click unsubscribe URL generation")
        return ""
    token = build_oneclick_unsubscribe_token(member_or_id)
    return f"{backend_url}/mail/unsubscribe/{token}/"
