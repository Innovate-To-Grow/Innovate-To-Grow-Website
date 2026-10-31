"""Access tokens for Microsoft Graph from the OAuth2 client-credentials grant with a certificate (``private_key_jwt``).

Tokens live only in process memory: they can send mail as any mailbox the app may use, so they must never reach
the shared cache (file-based in production) or disk. Each process fetches its own roughly hourly.

The certificate's private key never sits in this process between requests: on a token-cache miss it is read from
the credential store by the exact version the installed certificate pins, checked against the certificate's public
key, used to sign one client assertion and dropped.
"""

import json
import re
import threading
import time
from dataclasses import dataclass
from urllib.parse import quote, urlencode

from cryptography.exceptions import UnsupportedAlgorithm
from django.views.decorators.debug import sensitive_variables

from apps.core.services.credential_store import CredentialStoreError

from ..exceptions import PermanentEmailDeliveryError, TransientEmailDeliveryError
from . import transport
from .certificate import build_client_assertion
from .credential import stored_key
from .errors import token_endpoint_error

AUTHORITY_HOST = transport.AUTHORITY_HOST
RESOURCE_SCOPE = "https://graph.microsoft.com/.default"
REQUEST_TIMEOUT = 30
EXPIRY_MARGIN_SECONDS = 300
MAX_LIFETIME_SECONDS = 86400
# JWT / base64url alphabet: anything else could not be sent as a header value and must never be echoed in errors.
_ACCESS_TOKEN_RE = re.compile(r"[A-Za-z0-9._~+/=-]{1,16384}")

CLIENT_ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"

_cache: dict[tuple[str, str, str, str], tuple[str, float]] = {}
_cache_lock = threading.Lock()


@dataclass(frozen=True)
class GraphCredential:
    """Which Entra app and installed certificate to authenticate with. It holds no secret.

    ``key_arn`` and ``key_version_id`` pin the stored private key; ``public_key_sha256`` is the certificate's public
    key hash that the stored key must match, and ``x5t_s256`` the thumbprint each assertion names.
    """

    tenant_id: str
    client_id: str
    x5t_s256: str
    public_key_sha256: str
    key_arn: str
    key_version_id: str

    def cache_key(self) -> tuple[str, str, str, str]:
        # Installing or rolling back a certificate changes the version or thumbprint, so a token minted with
        # another certificate is never reused.
        return self.tenant_id, self.client_id, self.key_version_id, self.x5t_s256


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


def post_token_request(tenant_id: str, client_id: str, assertion: str, *, timeout: float) -> transport.HttpResponse:
    """POST the client-credentials grant. Raises ``transport.ConnectFailed`` / ``transport.ResponseLost``."""
    form = {
        "client_id": client_id,
        "client_assertion_type": CLIENT_ASSERTION_TYPE,
        "client_assertion": assertion,
        "scope": RESOURCE_SCOPE,
        "grant_type": "client_credentials",
    }
    path = f"/{quote(tenant_id, safe='')}/oauth2/v2.0/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}
    return transport.post(AUTHORITY_HOST, path, urlencode(form).encode("ascii"), headers, timeout=timeout)


def parse_access_token(body: bytes) -> tuple[str, int]:
    """The token and its lifetime from a 200 answer; an unreadable answer is transient."""
    try:
        data = json.loads(body)
        access_token = data["access_token"]
        lifetime = max(0, min(int(data.get("expires_in", 0)), MAX_LIFETIME_SECONDS))
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError, RecursionError):
        access_token, lifetime = "", 0
    if not isinstance(access_token, str) or not _ACCESS_TOKEN_RE.fullmatch(access_token):
        raise TransientEmailDeliveryError("Microsoft identity platform returned an unreadable response.")
    return access_token, lifetime


def _request_access_token(credential: GraphCredential, timeout: float) -> tuple[str, int]:
    assertion = _signed_assertion(credential)
    try:
        response = post_token_request(credential.tenant_id, credential.client_id, assertion, timeout=timeout)
    except transport.ConnectFailed as exc:
        if exc.verification_failed:
            raise PermanentEmailDeliveryError("TLS verification of the Microsoft identity platform failed.") from exc
        raise TransientEmailDeliveryError("Microsoft identity platform could not be reached.") from exc
    except transport.ResponseLost as exc:
        # A token request sends no mail, so repeating it is always safe.
        raise TransientEmailDeliveryError("Microsoft identity platform did not answer.") from exc
    if response.status != 200:
        raise token_endpoint_error(response)
    return parse_access_token(response.body)


@sensitive_variables()
def _signed_assertion(credential: GraphCredential) -> str:
    """Read the pinned key, sign one assertion, and let the key go out of scope."""
    error = None
    try:
        private_key = stored_key.read_key(
            arn=credential.key_arn,
            version_id=credential.key_version_id,
            expected_public_key_sha256=credential.public_key_sha256,
        )
    except CredentialStoreError as exc:
        error_class = TransientEmailDeliveryError if exc.transient else PermanentEmailDeliveryError
        error = error_class(f"The Microsoft Graph private key could not be read: {exc}")
    if error is not None:
        raise error
    try:
        return build_client_assertion(
            tenant_id=credential.tenant_id,
            client_id=credential.client_id,
            private_key=private_key,
            x5t_s256=credential.x5t_s256,
        )
    except (ValueError, TypeError, UnsupportedAlgorithm):
        raise PermanentEmailDeliveryError("The Microsoft Graph certificate private key could not be used.") from None
