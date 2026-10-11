"""Hardened response cookies for the isolated Legacy viewer session."""

import math

from django.http import HttpResponse
from django.utils import timezone

from .contracts import (
    LEGACY_VIEWER_COOKIE_NAME,
    LEGACY_VIEWER_COOKIE_PATH,
    LEGACY_VIEWER_TTL_SECONDS,
    LegacyViewerSession,
)


def set_legacy_viewer_cookie(response: HttpResponse, viewer_session: LegacyViewerSession) -> None:
    """Attach the hardened CloudFront-domain viewer cookie to ``response``."""

    max_age = max(1, math.ceil((viewer_session.expires_at - timezone.now()).total_seconds()))
    response.set_cookie(
        LEGACY_VIEWER_COOKIE_NAME,
        viewer_session.session_key,
        max_age=min(max_age, LEGACY_VIEWER_TTL_SECONDS),
        path=LEGACY_VIEWER_COOKIE_PATH,
        secure=True,
        httponly=True,
        samesite="Lax",
    )


def clear_legacy_viewer_cookie(response: HttpResponse) -> None:
    """Expire the viewer cookie with the same security attributes."""

    # Django 5.2's ``delete_cookie`` does not expose ``secure``/``httponly``.
    response.set_cookie(
        LEGACY_VIEWER_COOKIE_NAME,
        value="",
        max_age=0,
        expires="Thu, 01 Jan 1970 00:00:00 GMT",
        path=LEGACY_VIEWER_COOKIE_PATH,
        secure=True,
        httponly=True,
        samesite="Lax",
    )
