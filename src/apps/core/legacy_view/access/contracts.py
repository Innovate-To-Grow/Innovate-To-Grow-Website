"""Constants and value objects for Legacy viewer authorization."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.core.exceptions import PermissionDenied

from apps.core.models import LegacyAccessGrant

LEGACY_ACCESS_CODE_TTL_SECONDS = 60
LEGACY_VIEWER_TTL_SECONDS = 60 * 60
LEGACY_VIEWER_COOKIE_NAME = "i2g_legacy_viewer"
LEGACY_VIEWER_COOKIE_PATH = "/"


class LegacyViewerAccessDenied(PermissionDenied):
    """The request does not carry a currently valid legacy-viewer session."""


@dataclass(frozen=True)
class IssuedLegacyAccessGrant:
    """The raw code returned once to the launch page plus its durable record."""

    grant: LegacyAccessGrant
    code: str


@dataclass(frozen=True)
class LegacyViewerSession:
    """A newly created independent viewer session."""

    user: Any
    session_key: str
    expires_at: datetime
