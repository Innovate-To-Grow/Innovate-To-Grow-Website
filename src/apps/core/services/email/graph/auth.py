"""Access tokens for Microsoft Graph from the OAuth2 client-credentials grant (certificate or client secret).

Tokens live only in process memory: they can send mail as any mailbox the app may use, so they must never reach
the shared cache (file-based in production) or disk. Each process fetches its own roughly hourly.
"""

import hashlib
import json
import re
import threading
import time
from dataclasses import dataclass, field
from urllib.parse import quote, urlencode

from ..exceptions import PermanentEmailDeliveryError, TransientEmailDeliveryError
from . import transport
from .certificate import CertificateError, build_client_assertion
from .errors import token_endpoint_error

AUTHORITY_HOST = "login.microsoftonline.com"
RESOURCE_SCOPE = "https://graph.microsoft.com/.default"
REQUEST_TIMEOUT = 30
EXPIRY_MARGIN_SECONDS = 300
MAX_LIFETIME_SECONDS = 86400
# JWT / base64url alphabet: anything else could not be sent as a header value and must never be echoed in errors.
_ACCESS_TOKEN_RE = re.compile(r"[A-Za-z0-9._~+/=-]{1,16384}")

CLIENT_ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"

_cache: dict[tuple[str, str, str], tuple[str, float]] = {}
_cache_lock = threading.Lock()


@dataclass(frozen=True)
class GraphCredential:
    """An Entra application credential: a certificate (private key + thumbprint) or a client secret.

    Secret material is excluded from ``repr`` so a credential can never leak through a log line or traceback.
    """

    tenant_id: str
    client_id: str
    client_secret: str = field(default="", repr=False)
    private_key_pem: str = field(default="", repr=False)
    certificate_thumbprint: str = ""

    @property
    def uses_certificate(self) -> bool:
        return bool(self.private_key_pem)

    def cache_key(self) -> tuple[str, str, str]:
        # Hashing the secret material means rotating it can never reuse a token minted with the old one.
        material = (
            f"{self.certificate_thumbprint}:{self.private_key_pem}" if self.uses_certificate else self.client_secret
        )
        return self.tenant_id, self.client_id, hashlib.sha256(material.encode()).hexdigest()

    def authentication_fields(self) -> dict[str, str]:
        if not self.uses_certificate:
            return {"client_secret": self.client_secret}
        try:
            assertion = build_client_assertion(
                tenant_id=self.tenant_id,
                client_id=self.client_id,
                private_key_pem=self.private_key_pem,
                thumbprint=self.certificate_thumbprint,
            )
        except (CertificateError, ValueError, TypeError) as exc:
            raise PermanentEmailDeliveryError("The Microsoft Graph certificate private key could not be used.") from exc
        return {"client_assertion_type": CLIENT_ASSERTION_TYPE, "client_assertion": assertion}


def clear_access_token_cache() -> None:
    with _cache_lock:
        _cache.clear()


def forget_access_token(credential: GraphCredential) -> None:
    """Drop the cached token after Graph rejected it, so the next request fetches a fresh one."""
    with _cache_lock:
        _cache.pop(credential.cache_key(), None)


def get_access_token(credential: GraphCredential, *, timeout: float = REQUEST_TIMEOUT) -> str:
    """Return a valid Graph access token, requesting one from the Microsoft identity platform when needed.

    Every failure here happens before any mail is submitted, so it is always safely classified (never Uncertain).
    """
    key = credential.cache_key()
    with _cache_lock:
        cached = _cache.get(key)
    if cached is not None and cached[1] > time.monotonic():
        return cached[0]
    access_token, lifetime = _request_access_token(credential, timeout)
    ttl = lifetime - EXPIRY_MARGIN_SECONDS if lifetime > 2 * EXPIRY_MARGIN_SECONDS else lifetime // 2
    if ttl > 0:
        with _cache_lock:
            _cache[key] = (access_token, time.monotonic() + ttl)
    return access_token


def _request_access_token(credential: GraphCredential, timeout: float) -> tuple[str, int]:
    form = {"client_id": credential.client_id, **credential.authentication_fields()}
    body = urlencode({**form, "scope": RESOURCE_SCOPE, "grant_type": "client_credentials"}).encode("ascii")
    path = f"/{quote(credential.tenant_id, safe='')}/oauth2/v2.0/token"
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
