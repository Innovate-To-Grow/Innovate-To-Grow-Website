"""Issuance and atomic consumption of one-time Legacy access codes."""

import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac

from apps.core.models import LegacyAccessGrant
from apps.core.utils.access import user_can_access_app

from .contracts import (
    LEGACY_ACCESS_CODE_TTL_SECONDS,
    IssuedLegacyAccessGrant,
    LegacyViewerAccessDenied,
    LegacyViewerSession,
)
from .sessions import (
    create_viewer_session,
    database_session_expiry,
    source_session_is_valid,
)


def _digest_code(code: str) -> str:
    return salted_hmac(
        "core.legacy-access-grant",
        code,
        secret=settings.SECRET_KEY,
        algorithm="sha256",
    ).hexdigest()


def issue_legacy_access_grant(request) -> IssuedLegacyAccessGrant:
    """Create a one-minute, one-time code bound to the current admin session."""

    user = request.user
    if not user_can_access_app(user, "core"):
        raise LegacyViewerAccessDenied("Core admin access is required.")

    source_session_key = request.session.session_key
    if not source_session_key:
        raise LegacyViewerAccessDenied("A persisted admin session is required.")

    now = timezone.now()
    source_expires_at = database_session_expiry(source_session_key)
    if not source_session_is_valid(user, source_session_key, source_expires_at, now=now):
        raise LegacyViewerAccessDenied("The source admin session is no longer valid.")

    code = secrets.token_urlsafe(48)
    expires_at = min(
        now + timedelta(seconds=LEGACY_ACCESS_CODE_TTL_SECONDS),
        source_expires_at,
    )
    if expires_at <= now:
        raise LegacyViewerAccessDenied("The source admin session is about to expire.")

    grant = LegacyAccessGrant.objects.create(
        user=user,
        code_digest=_digest_code(code),
        source_session_key=source_session_key,
        source_session_expires_at=source_expires_at,
        expires_at=expires_at,
    )
    return IssuedLegacyAccessGrant(grant=grant, code=code)


def exchange_legacy_access_code(code: str) -> LegacyViewerSession:
    """Atomically consume ``code`` and create an independent viewer session."""

    if not isinstance(code, str) or not code or len(code) > 256:
        raise LegacyViewerAccessDenied("The access code is invalid or expired.")

    now = timezone.now()
    digest = _digest_code(code)
    with transaction.atomic():
        consumed = LegacyAccessGrant.objects.filter(
            code_digest=digest,
            consumed_at__isnull=True,
            expires_at__gt=now,
        ).update(consumed_at=now, updated_at=now)
        if consumed != 1:
            raise LegacyViewerAccessDenied("The access code is invalid or expired.")
        grant = LegacyAccessGrant.objects.select_related("user").get(code_digest=digest)

    user = grant.user
    if not user_can_access_app(user, "core") or not source_session_is_valid(
        user,
        grant.source_session_key,
        grant.source_session_expires_at,
        now=now,
    ):
        raise LegacyViewerAccessDenied("The source admin session is no longer valid.")

    return create_viewer_session(
        user,
        grant.source_session_key,
        grant.source_session_expires_at,
        now=now,
    )
