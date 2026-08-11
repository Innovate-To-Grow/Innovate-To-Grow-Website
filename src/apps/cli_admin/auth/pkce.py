import base64
import hashlib

from django.utils.crypto import constant_time_compare


def verify_pkce_s256(code_verifier: str, code_challenge: str) -> bool:
    """Return True iff BASE64URL(SHA256(code_verifier)) == code_challenge.

    Implements the RFC 7636 §4.6 S256 verification. The comparison is
    constant-time so a mismatch leaks no timing information.
    """
    if not code_verifier or not code_challenge:
        return False
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return constant_time_compare(expected, code_challenge)
