"""Access tokens for Microsoft Graph from the OAuth2 client-credentials grant.

Tokens live only in process memory: they can send mail as any mailbox the app may use, so they must never reach
the shared cache (file-based in production) or disk. Each process fetches its own roughly hourly.
"""

import hashlib
import json
import re
import threading
import time
from urllib.parse import quote, urlencode

from ..exceptions import PermanentEmailDeliveryError, TransientEmailDeliveryError
from . import transport
from .errors import token_endpoint_error

AUTHORITY_HOST = "login.microsoftonline.com"
RESOURCE_SCOPE = "https://graph.microsoft.com/.default"
REQUEST_TIMEOUT = 30
EXPIRY_MARGIN_SECONDS = 300
MAX_LIFETIME_SECONDS = 86400
# JWT / base64url alphabet: anything else could not be sent as a header value and must never be echoed in errors.
_ACCESS_TOKEN_RE = re.compile(r"[A-Za-z0-9._~+/=-]{1,16384}")

_cache: dict[tuple[str, str, str], tuple[str, float]] = {}
_cache_lock = threading.Lock()


def _cache_key(tenant_id: str, client_id: str, client_secret: str) -> tuple[str, str, str]:
    # Hashing the secret means rotating it in the admin can never reuse a token minted with the old one.
    return tenant_id, client_id, hashlib.sha256(client_secret.encode()).hexdigest()


def clear_access_token_cache() -> None:
    with _cache_lock:
        _cache.clear()


def forget_access_token(tenant_id: str, client_id: str, client_secret: str) -> None:
    """Drop the cached token after Graph rejected it, so the next send fetches a fresh one."""
    with _cache_lock:
        _cache.pop(_cache_key(tenant_id, client_id, client_secret), None)


def get_access_token(tenant_id: str, client_id: str, client_secret: str, *, timeout: float = REQUEST_TIMEOUT) -> str:
    """Return a valid Graph access token, requesting one from the Microsoft identity platform when needed.

    Every failure here happens before any mail is submitted, so it is always safely classified (never Uncertain).
    """
    key = _cache_key(tenant_id, client_id, client_secret)
    with _cache_lock:
        cached = _cache.get(key)
    if cached is not None and cached[1] > time.monotonic():
        return cached[0]
    access_token, lifetime = _request_access_token(tenant_id, client_id, client_secret, timeout)
    ttl = lifetime - EXPIRY_MARGIN_SECONDS if lifetime > 2 * EXPIRY_MARGIN_SECONDS else lifetime // 2
    if ttl > 0:
        with _cache_lock:
            _cache[key] = (access_token, time.monotonic() + ttl)
    return access_token


def _request_access_token(tenant_id: str, client_id: str, client_secret: str, timeout: float) -> tuple[str, int]:
    body = urlencode(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": RESOURCE_SCOPE,
            "grant_type": "client_credentials",
        }
    ).encode("ascii")
    path = f"/{quote(tenant_id, safe='')}/oauth2/v2.0/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}
    try:
        response = transport.post(AUTHORITY_HOST, path, body, headers, timeout=timeout)
    except transport.ConnectFailed as exc:
        if exc.verification_failed:
            raise PermanentEmailDeliveryError("TLS verification of the Microsoft identity platform failed.") from exc
        raise TransientEmailDeliveryError("Microsoft identity platform could not be reached.") from exc
    except transport.ResponseLost as exc:
        # A token request sends no mail, so repeating it is always safe.
        raise TransientEmailDeliveryError("Microsoft identity platform did not answer.") from exc
    if response.status != 200:
        raise token_endpoint_error(response)
    return _parse_access_token(response.body)


def _parse_access_token(body: bytes) -> tuple[str, int]:
    try:
        data = json.loads(body)
        access_token = data["access_token"]
        lifetime = max(0, min(int(data.get("expires_in", 0)), MAX_LIFETIME_SECONDS))
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError, RecursionError):
        access_token, lifetime = "", 0
    if not isinstance(access_token, str) or not _ACCESS_TOKEN_RE.fullmatch(access_token):
        raise TransientEmailDeliveryError("Microsoft identity platform returned an unreadable response.")
    return access_token, lifetime
