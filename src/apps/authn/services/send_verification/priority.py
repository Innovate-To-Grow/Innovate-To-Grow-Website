"""Is an anonymous code request user-initiated? The request limiter's priority check for the P0 code-send scope.

The normal UI flow sends a solved ALTCHA proof with every anonymous code request, so a request is promoted to P0
only when its body carries the three proof fields and the proof verifies: unexpired, signed by this server (current
or previous secret), solved, and signed for the challenge the body names. Nothing is consumed or written (the view
spends the challenge as before), and a payload that is not signed by this server fails at its first HMAC, so junk
costs no key derivation. A signed-in person is promoted by the limiter itself; anything else is not promoted.

The answer is the challenge id, so the limiter promotes one solved proof only a few times (a replayed body is
counted as unproven after that). Each verdict is remembered for ``VERDICT_SECONDS`` per payload in this process, so
replaying one body costs neither the settings query nor the key derivation again.
"""

import hashlib
import json
import logging
import threading
import time

from django.http.request import RawPostDataException

from .config import load_settings
from .guard import extract_verification_fields
from .proofs import payload_parameters, verify_payload

logger = logging.getLogger(__name__)

# Bodies above this are never parsed here (a code request with its proof is a few kilobytes).
MAX_BODY_BYTES = 64 * 1024
# How long one payload's verdict is remembered, and for how many payloads at most (then all are forgotten).
VERDICT_SECONDS = 30
MAX_VERDICTS = 1_024

_VERDICTS: dict[str, tuple[float, str | None]] = {}
_LOCK = threading.Lock()


def _content_length(request) -> int:
    try:
        return int(request.META.get("CONTENT_LENGTH") or 0)
    except (TypeError, ValueError):
        return 0


def _body(request):
    """The request's fields (JSON object or form), or None."""
    if not 0 < _content_length(request) <= MAX_BODY_BYTES:
        return None
    if (request.content_type or "").lower() == "application/json":
        try:
            data = json.loads(request.body or b"{}")
        except (ValueError, UnicodeDecodeError, RawPostDataException):
            return None
        return data if isinstance(data, dict) else None
    return request.POST


def _verdict(challenge_id: str, payload: str) -> str | None:
    try:
        verify_payload(payload, load_settings())
        signed = payload_parameters(payload).get("data") or {}
    except Exception:  # noqa: BLE001 - any invalid, expired or unreadable proof is simply not promoted.
        return None
    if isinstance(signed, dict) and str(signed.get("challenge_id") or "") == challenge_id:
        return challenge_id
    return None


def _now() -> float:
    return time.monotonic()


def _remembered(challenge_id: str, payload: str) -> str | None:
    name = hashlib.blake2b(f"{challenge_id}|{payload}".encode(), digest_size=16).hexdigest()
    now = _now()
    with _LOCK:
        known = _VERDICTS.get(name)
    if known is not None and known[0] > now:
        return known[1]
    verdict = _verdict(challenge_id, payload)
    with _LOCK:
        if len(_VERDICTS) >= MAX_VERDICTS:
            _VERDICTS.clear()
        _VERDICTS[name] = (now + VERDICT_SECONDS, verdict)
    return verdict


def forget_verdicts() -> None:
    with _LOCK:
        _VERDICTS.clear()


def carries_valid_proof(request) -> str | None:
    """The challenge id when the request carries a verified send-verification proof for the challenge it names."""
    data = _body(request)
    if data is None:
        return None
    challenge_id, payload, request_id = extract_verification_fields(data)
    if not (challenge_id and payload and request_id):
        return None
    return _remembered(str(challenge_id), payload)
