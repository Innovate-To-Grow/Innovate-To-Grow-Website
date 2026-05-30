import base64
import hashlib
import secrets


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def generate_verifier() -> str:
    """Return a high-entropy PKCE code_verifier (86 chars, within RFC 7636's 43-128)."""
    return _b64url(secrets.token_bytes(64))


def challenge_s256(verifier: str) -> str:
    """Return BASE64URL(SHA256(verifier)) — must match the backend's verify_pkce_s256."""
    return _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
