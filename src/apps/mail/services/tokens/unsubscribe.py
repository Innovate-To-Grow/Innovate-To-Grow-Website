"""RFC 8058 one-click unsubscribe and resubscribe token utilities."""

import logging
import uuid

from django.conf import settings
from django.core import signing

logger = logging.getLogger(__name__)

# Payload and salt are part of every unsubscribe link already in an inbox: changing either breaks those links.
_SALT = "rfc8058-one-click-unsubscribe"
# Reusable for a year (unsubscribing is idempotent). Links are signed with SECRET_KEY, so rotating it without
# SECRET_KEY_FALLBACKS invalidates every link in old newsletters.
_MAX_AGE = 60 * 60 * 24 * 365  # 365 days


def build_oneclick_unsubscribe_token(member_or_id) -> str:
    """Create a signed token encoding the member's PK.

    Accepts a Member instance or a raw UUID/string PK.
    """
    pk = str(member_or_id.pk if hasattr(member_or_id, "pk") else member_or_id)
    return signing.dumps({"member_id": pk}, salt=_SALT, compress=True)


def get_member_from_oneclick_token(token: str):
    """Validate a one-click unsubscribe token and return the Member.

    The token is reusable until it expires, and inactive members are returned too: anyone may always opt out.
    Raises ``ValueError`` on invalid, expired, or unknown-member tokens.
    """
    from apps.authn.models import Member

    try:
        payload = signing.loads(token, salt=_SALT, max_age=_MAX_AGE)
        member_id = payload["member_id"]
    except (signing.BadSignature, KeyError, TypeError) as exc:
        raise ValueError("Invalid or expired unsubscribe link.") from exc

    try:
        return Member.objects.get(pk=member_id)
    except Member.DoesNotExist as exc:
        raise ValueError("Account not found.") from exc


_RESUBSCRIBE_SALT = "mail-resubscribe"
_RESUBSCRIBE_MAX_AGE = 60 * 60  # 1 hour


def build_resubscribe_token(member_or_id, email_ids=None) -> str:
    """Create a short-lived signed token for re-subscribing.

    ``email_ids`` are the contact emails the unsubscribe turned off. Without them the token restores only the
    primary address, like the tokens issued before per-address resubscribe; an empty list is refused so a token
    can never silently fall back to that behaviour.
    """
    pk = str(member_or_id.pk if hasattr(member_or_id, "pk") else member_or_id)
    payload = {"member_id": pk}
    if email_ids is not None:
        if not email_ids:
            raise ValueError("A resubscribe token needs at least one email id.")
        payload["email_ids"] = [str(email_id) for email_id in email_ids]
    return signing.dumps(payload, salt=_RESUBSCRIBE_SALT, compress=True)


def load_resubscribe_token(token: str):
    """Validate a resubscribe token and return ``(member, email_ids)``.

    ``email_ids`` is ``None`` for a token without the key (issued before per-address resubscribe): the caller
    falls back to the primary address. Raises ``ValueError`` on invalid, expired, or unknown-member tokens.
    """
    from apps.authn.models import Member

    try:
        payload = signing.loads(token, salt=_RESUBSCRIBE_SALT, max_age=_RESUBSCRIBE_MAX_AGE)
        member_id = payload["member_id"]
        email_ids = payload.get("email_ids")
        if email_ids is not None:
            if not isinstance(email_ids, list):
                raise TypeError("email_ids must be a list")
            email_ids = [str(uuid.UUID(str(email_id))) for email_id in email_ids]
    except (signing.BadSignature, KeyError, TypeError, ValueError) as exc:
        raise ValueError("Invalid or expired resubscribe link.") from exc

    try:
        member = Member.objects.get(pk=member_id, is_active=True)
    except Member.DoesNotExist as exc:
        raise ValueError("Account not found.") from exc
    return member, email_ids


def get_member_from_resubscribe_token(token: str):
    """Validate a resubscribe token and return the Member.

    Raises ``ValueError`` on invalid, expired, or unknown-member tokens.
    """
    return load_resubscribe_token(token)[0]


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
