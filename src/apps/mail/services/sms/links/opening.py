"""Opening an SMS short link: where its token sends the visitor, and claiming a personal link."""

from dataclasses import dataclass

from django.db.models import F
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.mail.models import SmsLinkToken
from apps.mail.models.sms_config import revoke_personal_links
from apps.mail.models.sms_link import SmsLinkRevocation

from .issuing import TOKEN_RE, _still_owns, may_sign_in_by_sms, personal_link_state, sign_in_path, token_digest


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
    return _open_personal(link) if link.is_personal else _open_shared(link)


def _open_shared(link: SmsLinkToken) -> Opened:
    if link.revoked_at is not None or link.is_expired:
        return Opened("rejected", redirect_to=link.redirect_path, code="expired", reason="expired")
    now = timezone.now()
    SmsLinkToken.objects.filter(pk=link.pk).update(
        use_count=F("use_count") + 1, first_used_at=Coalesce("first_used_at", now), updated_at=now
    )
    return Opened("redirect", redirect_to=link.redirect_path)


def _open_personal(link: SmsLinkToken) -> Opened:
    if not may_sign_in_by_sms(link.member):
        return Opened("rejected", code="invalid_link", reason="member_not_allowed")
    if not _still_owns(link):
        # The phone it was texted to is no longer the member's own verified phone (removed, moved, recycled).
        return Opened("rejected", code="invalid_link", reason="phone_not_owned")
    state = personal_link_state()
    if link.revoked_at is not None or link.epoch != state.epoch:
        # Revoked: personal sign-in links were turned off after it was issued (whatever its row says now), or staff
        # revoked it. Checked before its expiry, which a revocation also sets.
        return _sign_in_page(link, "revoked")
    if not state.on:
        # Off, yet never revoked: they were turned off outside the app. Revoke every outstanding link now, so
        # turning them on again cannot bring this one or any other back.
        revoke_personal_links(via=SmsLinkRevocation.Via.LINK_OPENED)
        return _sign_in_page(link, "switched_off")
    if link.is_expired:
        return Opened("rejected", redirect_to=link.redirect_path, code="expired", reason="expired")
    if _claim(link):
        return Opened("sign_in", redirect_to=link.redirect_path, member=link.member)
    # Lost the claim: used by another click, or revoked while it was being opened.
    link.refresh_from_db(fields=["revoked_at"])
    if link.revoked_at is not None:
        return _sign_in_page(link, "revoked")
    return Opened("rejected", redirect_to=link.redirect_path, code="already_used", reason="already_used")


def _claim(link: SmsLinkToken) -> bool:
    """Take the link's one sign-in with one conditional UPDATE: two clicks cannot both sign in, and a revocation
    that commits first wins (its ``revoked_at``)."""
    now = timezone.now()
    unused = SmsLinkToken.objects.filter(
        pk=link.pk, first_used_at__isnull=True, revoked_at__isnull=True, expires_at__gt=now
    )
    return bool(unused.update(first_used_at=now, use_count=F("use_count") + 1, updated_at=now))


def _sign_in_page(link: SmsLinkToken, reason: str) -> Opened:
    """A personal link that signs nobody in: the sign-in page, which returns to its page; the link stays unused."""
    return Opened("redirect", redirect_to=sign_in_path(link.redirect_path), reason=reason)
