"""Django session loading for ADK web auth."""

from http import cookies
from importlib import import_module

from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth import HASH_SESSION_KEY, SESSION_KEY, get_user_model
from django.db import close_old_connections
from django.utils.crypto import constant_time_compare


async def load_staff_user_id_from_headers(headers) -> str | None:
    return await sync_to_async(_load_staff_user_id_from_headers_sync, thread_sensitive=True)(headers)


def _load_staff_user_id_from_headers_sync(headers) -> str | None:
    close_old_connections()
    try:
        session_key = _session_key_from_headers(headers)
        if not session_key:
            return None

        engine = import_module(settings.SESSION_ENGINE)
        session = engine.SessionStore(session_key=session_key)
        user_id = session.get(SESSION_KEY)
        if not user_id:
            return None

        try:
            user = get_user_model()._default_manager.get(pk=user_id)
        except get_user_model().DoesNotExist:
            return None

        if not user.is_active or not user.is_staff:
            return None

        session_hash = session.get(HASH_SESSION_KEY)
        if session_hash and hasattr(user, "get_session_auth_hash"):
            if not constant_time_compare(session_hash, user.get_session_auth_hash()):
                return None

        return str(user.pk)
    finally:
        close_old_connections()


def _session_key_from_headers(headers) -> str | None:
    cookie_header = "; ".join(value.decode("latin1") for name, value in headers if name.lower() == b"cookie")
    if not cookie_header:
        return None
    parsed = cookies.SimpleCookie()
    try:
        parsed.load(cookie_header)
    except cookies.CookieError:
        return None
    morsel = parsed.get(settings.SESSION_COOKIE_NAME)
    return morsel.value if morsel else None
