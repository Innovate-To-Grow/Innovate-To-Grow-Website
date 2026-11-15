"""Issuing the tokens behind SMS short links, and who may get a personal one."""

import hashlib
import re
import secrets
from datetime import timedelta
from urllib.parse import quote

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.authn.models import ContactPhone
from apps.mail.models import SmsConfig, SmsLinkToken
from apps.mail.models.sms_config import PersonalLinkState
from apps.mail.redirects import DEFAULT_LOGIN_REDIRECT_PATH, is_strict_internal_path

from ..policy.opt_outs import US_REGION, normalize_phone, us_national_digits

LINK_PATH = "/l/"
SIGN_IN_PATH = "/login"
EVENT_PAGE_PATH = "/event-registration"
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
Purpose = SmsLinkToken.Purpose


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def phone_digest(phone) -> str:
    number = normalize_phone(phone)
    return hashlib.sha256(number.encode("utf-8")).hexdigest() if number else ""


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
    if not is_strict_internal_path(destination) or destination == DEFAULT_LOGIN_REDIRECT_PATH:
        return SIGN_IN_PATH
    path = f"{SIGN_IN_PATH}?returnTo={quote(destination, safe='/')}"
    return path if len(path) <= 200 else SIGN_IN_PATH


def personal_link_state() -> PersonalLinkState:
    """Links in SMS, personal sign-in links and the epoch a personal link must carry, as they stand now (Mail → SMS
    Settings). Read when a personal link is issued and again when one is opened."""
    return SmsConfig.load().personal_link_state


def may_sign_in_by_sms(member) -> bool:
    """A personal sign-in link is issued only to an active member who is not staff (a recycled or shared phone must
    never open an admin account)."""
    return bool(member and member.is_active and not member.is_staff and not member.is_superuser)


def member_owns_phone(member, phone) -> bool:
    """``phone`` is one of ``member``'s own verified account phones: the only number a personal link may go to."""
    national = us_national_digits(normalize_phone(phone))
    if not member or not national:
        return False
    return ContactPhone.objects.filter(member=member, phone_number=national, region=US_REGION, verified=True).exists()


def may_text_personal_link(member, phone) -> bool:
    return may_sign_in_by_sms(member) and member_owns_phone(member, phone)


def _still_owns(link: SmsLinkToken) -> bool:
    if not link.phone_digest:
        return False
    phones = ContactPhone.objects.filter(member_id=link.member_id, region=US_REGION, verified=True)
    return any(phone_digest(phone.to_e164()) == link.phone_digest for phone in phones)


def _expiry(validity_days: int):
    days = max(1, min(int(validity_days), settings.SMS_POLICY["link_max_validity_days"]))
    return timezone.now() + timedelta(days=days)


def _new_token() -> str:
    return secrets.token_urlsafe(settings.SMS_POLICY["link_token_bytes"])


def issue_personal_link(
    *, purpose, member, phone, redirect_path, validity_days, campaign=None, registration=None
) -> str | None:
    """A one-time sign-in link for ``member``, texted to ``phone`` (their own verified phone), that lands on
    ``redirect_path``; its URL. None when personal sign-in links are off by now: the caller texts its sign-in page
    link instead. The link carries the epoch read with the switches, so if they go off before it is stored, it is
    dead on arrival."""
    if not may_text_personal_link(member, phone):
        raise ValueError("Personal SMS sign-in links go only to a member's own verified phone, never to staff.")
    state = personal_link_state()
    if not state.on:
        return None
    token = _new_token()
    SmsLinkToken.objects.create(
        token_hash=token_digest(token),
        purpose=purpose,
        member=member,
        campaign=campaign,
        registration=registration,
        redirect_path=redirect_path if is_strict_internal_path(redirect_path) else DEFAULT_LOGIN_REDIRECT_PATH,
        phone_digest=phone_digest(phone),
        epoch=state.epoch,
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
        redirect_path=redirect_path if is_strict_internal_path(redirect_path) else SIGN_IN_PATH,
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
                redirect_path=redirect_path if is_strict_internal_path(redirect_path) else SIGN_IN_PATH,
                expires_at=_expiry(validity_days),
            )
    except IntegrityError:
        # Another sender made it first (two workers): use theirs.
        existing = SmsLinkToken.objects.get(campaign=campaign, purpose=purpose, member__isnull=True)
        return link_url(existing.public_token)
    return link_url(token)


def revoke_links(queryset) -> int:
    """Revoke every still-valid link in ``queryset`` now: a shared one is refused as expired, a personal one opens
    the sign-in page."""
    now = timezone.now()
    return queryset.filter(expires_at__gt=now).update(expires_at=now, revoked_at=now, updated_at=now)
