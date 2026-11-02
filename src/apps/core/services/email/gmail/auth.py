"""Access tokens for the Gmail API: a service-account JWT assertion exchanged at Google's token endpoint.

Tokens live only in process memory, keyed by the service account, key id, pinned key version, subject and scope:
every part comes from the database row, so a cache hit never reads the key, and a rotated key never reuses a token
minted with the old one. They must never reach the shared cache (file-based in production) or disk.

On a miss the key is read from the credential store by its pinned version, checked against the recorded facts, used
to sign one assertion and dropped (Python cannot zero memory; nothing keeps a reference). Every failure here
happens before any mail is submitted, so it is always safely classified, never Uncertain.
"""

import json
import re
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlencode

from django.conf import settings
from django.views.decorators.debug import sensitive_variables

from apps.core.services.credential_store import CredentialStoreError
from apps.core.services.delivery_rates import pause
from apps.core.services.delivery_rates.adapters.gmail_api import store_signal

from ..exceptions import PermanentEmailDeliveryError, TransientEmailDeliveryError, with_signal
from . import transport
from .assertion import GMAIL_SEND_SCOPE, build_assertion
from .errors import token_error
from .key import stored_key
from .subject import AllowedSubject, require_issued

GRANT_TYPE = "urn:ietf:params:oauth:grant-type:jwt-bearer"
# JWT / base64url alphabet: anything else could not be sent as a header value and must never be echoed in errors.
_ACCESS_TOKEN_RE = re.compile(r"[A-Za-z0-9._~+/=-]{1,16384}")
UNREADABLE_ANSWER = "Google's token endpoint returned an unreadable response."
BROADER_SCOPE = "Google issued a token for another scope than requested; it was discarded."

_cache: dict[tuple[str, ...], tuple[str, float]] = {}
_cache_lock = threading.Lock()


@dataclass(frozen=True)
class GmailCredential:
    """Which service account and installed key to sign with. It holds no secret, only the pinned store version."""

    service_account_email: str
    client_id: str
    key_id: str
    key_ref: str
    key_version_id: str

    def cache_key(self, subject: str, scope: str) -> tuple[str, ...]:
        return self.service_account_email, self.key_id, self.key_version_id, subject, scope


@dataclass(frozen=True)
class TokenGrant:
    access_token: str = ""
    lifetime: int = 0

    def __repr__(self):
        return f"TokenGrant(lifetime={self.lifetime})"


def clear_access_token_cache() -> None:
    with _cache_lock:
        _cache.clear()


def forget_access_token(credential: GmailCredential, subject: AllowedSubject) -> None:
    """Drop the cached token after Gmail rejected it, so the next send mints a fresh one."""
    with _cache_lock:
        _cache.pop(credential.cache_key(subject.address, GMAIL_SEND_SCOPE), None)


def request_timeout(timeout: float | None = None) -> float:
    return settings.GMAIL_API["request_timeout_seconds"] if timeout is None else timeout


def get_access_token(credential: GmailCredential, subject: AllowedSubject, *, timeout=None) -> tuple[str, bool]:
    """A gmail.send token for *subject* and whether it was minted just now (a cache miss)."""
    require_issued(subject)
    key = credential.cache_key(subject.address, GMAIL_SEND_SCOPE)
    with _cache_lock:
        cached = _cache.get(key)
    if cached is not None and cached[1] > time.monotonic():
        return cached[0], False
    grant = request_token(credential, read_signing_key(credential), subject, timeout=request_timeout(timeout))
    margin = settings.GMAIL_API["token_expiry_margin_seconds"]
    ttl = grant.lifetime - margin if grant.lifetime > 2 * margin else grant.lifetime // 2
    if ttl > 0:
        with _cache_lock:
            _cache[key] = (grant.access_token, time.monotonic() + ttl)
    return grant.access_token, True


@sensitive_variables()
def read_signing_key(credential: GmailCredential):
    """The pinned key, checked against the recorded facts. A store failure is classified: busy is transient (pause
    and back off), a missing, refused or mismatched key permanent (a breaker until the configuration is saved)."""
    try:
        return stored_key.read_key(
            arn=credential.key_ref,
            version_id=credential.key_version_id,
            client_email=credential.service_account_email,
            key_id=credential.key_id,
        )
    except CredentialStoreError as exc:
        error_class = TransientEmailDeliveryError if exc.transient else PermanentEmailDeliveryError
        error = error_class(f"The Gmail API key could not be read: {exc}")
        signal = store_signal(transient=exc.transient)
    raise with_signal(error, signal)


@sensitive_variables()
def request_token(
    credential: GmailCredential, private_key, subject: AllowedSubject, *, timeout: float, scope=GMAIL_SEND_SCOPE
) -> TokenGrant:
    """One token request with *private_key* (already read) for *subject*. Never cached here."""
    require_issued(subject)
    assertion = build_assertion(
        client_email=credential.service_account_email,
        key_id=credential.key_id,
        private_key=private_key,
        subject=subject.address,
        scope=scope,
    )
    try:
        response = post_token_request(assertion, timeout=timeout)
    except transport.ConnectFailed as exc:
        if exc.verification_failed:
            raise PermanentEmailDeliveryError("TLS verification of Google's token endpoint failed.") from None
        raise _busy("Google's token endpoint could not be reached.") from None
    except transport.ResponseLost:
        # A token request sends no mail, so repeating it is always safe.
        raise _busy("Google's token endpoint did not answer.") from None
    if response.status != 200:
        raise token_error(response, client_id=credential.client_id)
    return parse_token(response.body, scope)


def _busy(message: str) -> TransientEmailDeliveryError:
    return with_signal(TransientEmailDeliveryError(message), pause("token_endpoint"))


@sensitive_variables()
def post_token_request(assertion: str, *, timeout: float) -> transport.HttpResponse:
    form = urlencode({"grant_type": GRANT_TYPE, "assertion": assertion}).encode("ascii")
    headers = {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}
    return transport.post(transport.TOKEN_HOST, transport.TOKEN_PATH, form, headers, timeout=timeout)


@sensitive_variables()
def parse_token(body: bytes, scope: str) -> TokenGrant:
    """The token and its lifetime from a 200 answer. An unreadable answer is transient; a token for any other scope
    than *scope*, or of another type than Bearer, is refused and dropped."""
    try:
        data = json.loads(body)
        access_token = data["access_token"]
        lifetime = max(0, min(int(data.get("expires_in", 0)), settings.GMAIL_API["token_max_lifetime_seconds"]))
        token_type = data.get("token_type", "Bearer")
        granted = data.get("scope", scope)
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError, RecursionError):
        access_token, lifetime, token_type, granted = "", 0, "", ""
    if not isinstance(access_token, str) or not _ACCESS_TOKEN_RE.fullmatch(access_token):
        raise TransientEmailDeliveryError(UNREADABLE_ANSWER)
    if not isinstance(token_type, str) or token_type.lower() != "bearer":
        raise PermanentEmailDeliveryError("Google issued a token of another type than Bearer; it was discarded.")
    if not isinstance(granted, str) or set(granted.split()) != {scope}:
        raise PermanentEmailDeliveryError(BROADER_SCOPE)
    return TokenGrant(access_token=access_token, lifetime=lifetime)
