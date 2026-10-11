"""Creation and per-request validation of isolated Legacy viewer sessions."""

import math
from datetime import UTC, datetime, timedelta
from importlib import import_module

from django.conf import settings
from django.contrib.auth import HASH_SESSION_KEY, SESSION_KEY, get_user_model
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.crypto import constant_time_compare

from apps.core.utils.access import user_can_access_app

from .config import legacy_view_is_enabled
from .contracts import LEGACY_VIEWER_TTL_SECONDS, LegacyViewerAccessDenied, LegacyViewerSession

_VIEWER_SESSION_VERSION = 1
_VIEWER_VERSION_KEY = "legacy_viewer_version"
_VIEWER_USER_KEY = "legacy_viewer_user_id"
_VIEWER_SOURCE_SESSION_KEY = "legacy_viewer_source_session_key"
_VIEWER_SOURCE_EXPIRES_KEY = "legacy_viewer_source_expires_at"
_VIEWER_EXPIRES_KEY = "legacy_viewer_expires_at"


def _session_store(session_key=None):
    engine = import_module(settings.SESSION_ENGINE)
    return engine.SessionStore(session_key=session_key)


def database_session_expiry(session_key: str):
    """Return the authoritative expiry of this project's DB-backed session."""

    try:
        return Session.objects.only("expire_date").get(session_key=session_key).expire_date
    except Session.DoesNotExist as exc:
        raise LegacyViewerAccessDenied("The source admin session is unavailable.") from exc


def _load_session(session_key: str) -> dict | None:
    if not session_key or len(session_key) > 128:
        return None
    try:
        store = _session_store(session_key)
        if store.session_key != session_key:
            return None
        data = store.load()
    except Exception:  # Fail closed for an unavailable or unsupported session backend.
        return None
    return data or None


def source_session_is_valid(user, session_key: str, expires_at, *, now=None) -> bool:
    now = now or timezone.now()
    if not expires_at or expires_at <= now:
        return False
    data = _load_session(session_key)
    if data is None or str(data.get(SESSION_KEY, "")) != str(user.pk):
        return False

    stored_hash = data.get(HASH_SESSION_KEY)
    if not stored_hash:
        return False
    return constant_time_compare(stored_hash, user.get_session_auth_hash())


def create_viewer_session(user, source_session_key: str, source_expires_at, *, now) -> LegacyViewerSession:
    expires_at = min(
        now + timedelta(seconds=LEGACY_VIEWER_TTL_SECONDS),
        source_expires_at,
    )
    remaining_seconds = math.floor((expires_at - now).total_seconds())
    if remaining_seconds < 1:
        raise LegacyViewerAccessDenied("The source admin session is about to expire.")

    viewer_store = _session_store()
    viewer_store.update(
        {
            _VIEWER_VERSION_KEY: _VIEWER_SESSION_VERSION,
            _VIEWER_USER_KEY: str(user.pk),
            _VIEWER_SOURCE_SESSION_KEY: source_session_key,
            _VIEWER_SOURCE_EXPIRES_KEY: source_expires_at.timestamp(),
            _VIEWER_EXPIRES_KEY: expires_at.timestamp(),
        }
    )
    viewer_store.set_expiry(remaining_seconds)
    viewer_store.create()
    return LegacyViewerSession(
        user=user,
        session_key=viewer_store.session_key,
        expires_at=expires_at,
    )


def _discard_viewer_session(session_key: str) -> None:
    try:
        _session_store(session_key).delete(session_key)
    except Exception:
        # Access is already denied; cleanup must not reveal backend details.
        return


def require_legacy_viewer(request):
    """Return the viewer user or raise after revalidating every security gate."""

    if not legacy_view_is_enabled():
        raise LegacyViewerAccessDenied("Legacy viewer access is disabled.")

    cached_user = getattr(request, "_i2g_legacy_viewer_user", None)
    if cached_user is not None:
        return cached_user

    viewer_session_key = request.COOKIES.get("i2g_legacy_viewer", "")
    data = _load_session(viewer_session_key)
    if data is None or data.get(_VIEWER_VERSION_KEY) != _VIEWER_SESSION_VERSION:
        raise LegacyViewerAccessDenied("A valid legacy viewer session is required.")

    try:
        viewer_expires_at = float(data[_VIEWER_EXPIRES_KEY])
        source_expires_at = float(data[_VIEWER_SOURCE_EXPIRES_KEY])
        user_id = data[_VIEWER_USER_KEY]
        source_session_key = data[_VIEWER_SOURCE_SESSION_KEY]
    except (KeyError, TypeError, ValueError):
        _discard_viewer_session(viewer_session_key)
        raise LegacyViewerAccessDenied("A valid legacy viewer session is required.") from None

    now = timezone.now()
    if viewer_expires_at <= now.timestamp() or source_expires_at <= now.timestamp():
        _discard_viewer_session(viewer_session_key)
        raise LegacyViewerAccessDenied("The legacy viewer session has expired.")

    user_model = get_user_model()
    try:
        user = user_model._default_manager.get(pk=user_id)
    except (user_model.DoesNotExist, TypeError, ValueError, ValidationError):
        _discard_viewer_session(viewer_session_key)
        raise LegacyViewerAccessDenied("The legacy viewer session is no longer valid.") from None

    source_expiry = datetime.fromtimestamp(source_expires_at, tz=UTC)
    if not user_can_access_app(user, "core") or not source_session_is_valid(
        user,
        source_session_key,
        source_expiry,
        now=now,
    ):
        _discard_viewer_session(viewer_session_key)
        raise LegacyViewerAccessDenied("The legacy viewer session is no longer valid.")

    request._i2g_legacy_viewer_user = user
    return user
