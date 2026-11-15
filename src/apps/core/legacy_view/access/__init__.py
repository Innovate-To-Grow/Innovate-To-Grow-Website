"""Public API for short-lived, server-side Legacy viewer authorization."""

from .config import legacy_view_is_enabled
from .contracts import (
    LEGACY_ACCESS_CODE_TTL_SECONDS,
    LEGACY_VIEWER_COOKIE_NAME,
    LEGACY_VIEWER_COOKIE_PATH,
    LEGACY_VIEWER_TTL_SECONDS,
    IssuedLegacyAccessGrant,
    LegacyViewerAccessDenied,
    LegacyViewerSession,
)
from .cookies import clear_legacy_viewer_cookie, set_legacy_viewer_cookie
from .grants import exchange_legacy_access_code, issue_legacy_access_grant
from .sessions import require_legacy_viewer

__all__ = [
    "LEGACY_ACCESS_CODE_TTL_SECONDS",
    "LEGACY_VIEWER_COOKIE_NAME",
    "LEGACY_VIEWER_COOKIE_PATH",
    "LEGACY_VIEWER_TTL_SECONDS",
    "IssuedLegacyAccessGrant",
    "LegacyViewerAccessDenied",
    "LegacyViewerSession",
    "clear_legacy_viewer_cookie",
    "exchange_legacy_access_code",
    "issue_legacy_access_grant",
    "legacy_view_is_enabled",
    "require_legacy_viewer",
    "set_legacy_viewer_cookie",
]
