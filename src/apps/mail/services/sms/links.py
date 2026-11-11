"""SMS short links (``/l/<token>``): issuing the tokens behind ``{{login_link}}``, ``{{ticket_link}}`` and
``{{event_link}}``, and exchanging one when it is opened.

A token is ``SMS_POLICY["link_token_bytes"]`` random bytes (128 bits by default, 22 URL-safe characters), so the URL
holds no member, phone or event and cannot be guessed. Only its SHA-256 digest is stored, except for a shared link,
which signs nobody in. Every link expires; a personal one signs its member in once (``first_used_at`` is claimed
with one conditional UPDATE, so two clicks cannot both sign in) and is never issued to staff, a superuser or an
inactive member. Opening a link is limited by the request limiter's ``auth-email-link`` scope.
"""

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import quote

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.mail.models import SmsLinkToken
from apps.mail.redirects import DEFAULT_LOGIN_REDIRECT_PATH, is_safe_internal_redirect_path

LINK_PATH = "/l/"
SIGN_IN_PATH = "/login"
EVENT_PAGE_PATH = "/event-registration"
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
Purpose = SmsLinkToken.Purpose


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def link_url(token: str) -> str:
    frontend_url = (getattr(settings, "FRONTEND_URL", "") or "").strip().rstrip("/")
    return f"{frontend_url}{LINK_PATH}{token}"


def example_link() -> str:
    """A link as long as a real one, for previews and the cost estimate (it opens nothing)."""
    length = len(secrets.token_urlsafe(settings.SMS_POLICY["link_token_bytes"]))
    return link_url("x" * length)


def event_page_path(event) -> str:
    return f"{EVENT_PAGE_PATH}?event={quote(event.slug, safe='')}"


def sign_in_path(destination: str) -> str:
    """The sign-in page, returning to ``destination`` afterwards (what a link that signs nobody in opens)."""
    if not is_safe_internal_redirect_path(destination) or destination == DEFAULT_LOGIN_REDIRECT_PATH:
        return SIGN_IN_PATH
    path = f"{SIGN_IN_PATH}?returnTo={quote(destination, safe='/')}"
    return path if len(path) <= 200 else SIGN_IN_PATH


def may_sign_in_by_sms(member) -> bool:
    """A personal sign-in link is issued only to an active member who is not staff (a recycled or shared phone must
    never open an admin account)."""
    return bool(member and member.is_active and not member.is_staff and not member.is_superuser)


def _expiry(validity_days: int):
    days = max(1, min(int(validity_days), settings.SMS_POLICY["link_max_validity_days"]))
    return timezone.now() + timedelta(days=days)


def _new_token() -> str:
    return secrets.token_urlsafe(settings.SMS_POLICY["link_token_bytes"])


def issue_personal_link(*, purpose, member, redirect_path, validity_days, campaign=None, registration=None) -> str:
    """A one-time sign-in link for ``member`` that lands on ``redirect_path``; its URL."""
    if not may_sign_in_by_sms(member):
        raise ValueError("Personal SMS sign-in links are never issued to staff or inactive members.")
    token = _new_token()
    SmsLinkToken.objects.create(
        token_hash=token_digest(token),
        purpose=purpose,
        member=member,
        campaign=campaign,
        registration=registration,
        redirect_path=redirect_path if is_safe_internal_redirect_path(redirect_path) else DEFAULT_LOGIN_REDIRECT_PATH,
        expires_at=_expiry(validity_days),
    )
    return link_url(token)


def issue_redirect_link(*, purpose, redirect_path, validity_days, registration=None) -> str:
    """A link that signs nobody in and sends whoever opens it to ``redirect_path``; its URL."""
    token = _new_token()
    SmsLinkToken.objects.create(
        token_hash=token_digest(token),
        purpose=purpose,
        registration=registration,
        redirect_path=redirect_path if is_safe_internal_redirect_path(redirect_path) else SIGN_IN_PATH,
        expires_at=_expiry(validity_days),
    )
    return link_url(token)


def shared_link(*, campaign, purpose, redirect_path, validity_days) -> str:
    """The campaign's one link for ``purpose`` that signs nobody in (made on first use); its URL."""
    existing = SmsLinkToken.objects.filter(campaign=campaign, purpose=purpose, member__isnull=True).first()
    if existing is not None:
        return link_url(existing.public_token)
    token = _new_token()
    try:
        with transaction.atomic():
            SmsLinkToken.objects.create(
                token_hash=token_digest(token),
                public_token=token,
                purpose=purpose,
                campaign=campaign,
                redirect_path=redirect_path if is_safe_internal_redirect_path(redirect_path) else SIGN_IN_PATH,
                expires_at=_expiry(validity_days),
            )
    except IntegrityError:
        # Another sender made it first (two workers): use theirs.
        existing = SmsLinkToken.objects.get(campaign=campaign, purpose=purpose, member__isnull=True)
        return link_url(existing.public_token)
    return link_url(token)


def revoke_links(queryset) -> int:
    """Expire every still-valid link in ``queryset`` now."""
    now = timezone.now()
    return queryset.filter(expires_at__gt=now).update(expires_at=now, updated_at=now)


@dataclass(frozen=True)
class Opened:
    """The outcome of opening a link: ``sign_in`` (``member``), ``redirect``, or ``rejected`` with ``code``."""

    kind: str
    redirect_to: str = ""
    member: object = None
    code: str = ""
    reason: str = ""


def open_link(token: str) -> Opened:
    """Exchange ``token``: sign its member in once, or send the visitor on; never says whose link it was."""
    if not TOKEN_RE.fullmatch(token or ""):
        return Opened("rejected", code="invalid_link", reason="malformed")
    link = SmsLinkToken.objects.select_related("member").filter(token_hash=token_digest(token)).first()
    if link is None:
        return Opened("rejected", code="invalid_link", reason="unknown_token")
    if link.is_personal and not may_sign_in_by_sms(link.member):
        return Opened("rejected", code="invalid_link", reason="member_not_allowed")
    if link.is_expired:
        return Opened("rejected", redirect_to=link.redirect_path, code="expired", reason="expired")
    now = timezone.now()
    if not link.is_personal:
        SmsLinkToken.objects.filter(pk=link.pk).update(
            use_count=F("use_count") + 1, first_used_at=Coalesce("first_used_at", now), updated_at=now
        )
        return Opened("redirect", redirect_to=link.redirect_path)
    claimed = SmsLinkToken.objects.filter(pk=link.pk, first_used_at__isnull=True, expires_at__gt=now).update(
        first_used_at=now, use_count=F("use_count") + 1, updated_at=now
    )
    if not claimed:
        return Opened("rejected", redirect_to=link.redirect_path, code="already_used", reason="already_used")
    return Opened("sign_in", redirect_to=link.redirect_path, member=link.member)
