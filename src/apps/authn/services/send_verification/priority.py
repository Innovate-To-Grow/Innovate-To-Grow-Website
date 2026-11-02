"""Is an anonymous code request user-initiated? The request limiter's priority check for the P0 code-send scope.

The normal UI flow sends a solved ALTCHA proof with every anonymous code request, so a request is promoted to P0
only when its body carries the three proof fields and the proof verifies: unexpired, signed by this server (current
or previous secret), solved, and signed for the challenge the body names. Nothing is consumed or written (the view
spends the challenge as before), and a payload that is not signed by this server fails at its first HMAC, so junk
costs no key derivation. A signed-in person is promoted by the limiter itself; anything else is not promoted.
"""

import json
import logging

from django.http.request import RawPostDataException

from .config import load_settings
from .guard import extract_verification_fields
from .proofs import payload_parameters, verify_payload

logger = logging.getLogger(__name__)

# Bodies above this are never parsed here (a code request with its proof is a few kilobytes).
MAX_BODY_BYTES = 64 * 1024


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


def carries_valid_proof(request) -> bool:
    """True when the request carries a verified send-verification proof for the challenge it names."""
    data = _body(request)
    if data is None:
        return False
    challenge_id, payload, request_id = extract_verification_fields(data)
    if not (challenge_id and payload and request_id):
        return False
    try:
        verify_payload(payload, load_settings())
        signed = payload_parameters(payload).get("data") or {}
    except Exception:  # noqa: BLE001 - any invalid, expired or unreadable proof is simply not promoted.
        return False
    return isinstance(signed, dict) and str(signed.get("challenge_id") or "") == str(challenge_id)
