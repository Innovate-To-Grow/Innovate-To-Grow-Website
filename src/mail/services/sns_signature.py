"""
Verify AWS SNS HTTP(S) message signatures.

Follows https://docs.aws.amazon.com/sns/latest/dg/sns-verify-signature-of-message.html.
The webhook endpoint is intentionally public; genuine-origin trust is anchored
here via the signed envelope AWS POSTs. Signatures are validated against a
certificate whose URL is restricted to the amazonaws.com domain, preventing
SSRF to arbitrary hosts.
"""

import base64
import logging
import urllib.request
from urllib.parse import urlparse

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.x509 import load_pem_x509_certificate

logger = logging.getLogger(__name__)

_ALLOWED_CERT_HOST_SUFFIXES = (".amazonaws.com",)

_CERT_CACHE: dict[str, bytes] = {}
_CERT_CACHE_MAX = 16

_SIGNED_FIELDS_NOTIFICATION = ("Message", "MessageId", "Subject", "Timestamp", "TopicArn", "Type")
_SIGNED_FIELDS_SUBSCRIPTION = ("Message", "MessageId", "SubscribeURL", "Timestamp", "Token", "TopicArn", "Type")


class SnsVerificationError(Exception):
    """Raised when an SNS envelope fails signature verification."""


def _canonical_string(envelope: dict) -> bytes:
    msg_type = envelope.get("Type")
    if msg_type == "Notification":
        fields = _SIGNED_FIELDS_NOTIFICATION
    elif msg_type in ("SubscriptionConfirmation", "UnsubscribeConfirmation"):
        fields = _SIGNED_FIELDS_SUBSCRIPTION
    else:
        raise SnsVerificationError(f"Unknown Type: {msg_type!r}")

    lines: list[str] = []
    for key in fields:
        if key not in envelope:
            # Subject is optional on Notification; skip when absent.
            if key == "Subject" and msg_type == "Notification":
                continue
            raise SnsVerificationError(f"Missing field {key!r}")
        lines.append(key)
        lines.append(str(envelope[key]))
    return ("\n".join(lines) + "\n").encode("utf-8")


def _fetch_cert(cert_url: str) -> bytes:
    parsed = urlparse(cert_url)
    if parsed.scheme != "https":
        raise SnsVerificationError("SigningCertURL must be https")
    host = parsed.hostname or ""
    if not any(host.endswith(suffix) for suffix in _ALLOWED_CERT_HOST_SUFFIXES):
        raise SnsVerificationError(f"SigningCertURL host not allowed: {host!r}")
    if cert_url in _CERT_CACHE:
        return _CERT_CACHE[cert_url]

    with urllib.request.urlopen(cert_url, timeout=5) as resp:  # noqa: S310  # https + allowlist
        pem = resp.read()

    if len(_CERT_CACHE) >= _CERT_CACHE_MAX:
        _CERT_CACHE.clear()
    _CERT_CACHE[cert_url] = pem
    return pem


def verify_sns_message(envelope: dict, *, allowed_topic_arns: set[str] | None = None) -> None:
    """Raise SnsVerificationError when envelope is not a genuine SNS message.

    ``allowed_topic_arns`` — optional allowlist; when provided, reject messages
    whose ``TopicArn`` is not in the set.
    """
    cert_url = envelope.get("SigningCertURL") or envelope.get("SigningCertUrl") or ""
    signature_b64 = envelope.get("Signature") or ""
    signature_version = envelope.get("SignatureVersion") or "1"

    if signature_version not in ("1", "2"):
        raise SnsVerificationError(f"Unsupported SignatureVersion: {signature_version}")

    if allowed_topic_arns is not None:
        arn = envelope.get("TopicArn", "")
        if arn not in allowed_topic_arns:
            raise SnsVerificationError(f"TopicArn not allowed: {arn!r}")

    pem = _fetch_cert(cert_url)
    cert = load_pem_x509_certificate(pem)
    public_key = cert.public_key()
    try:
        signature = base64.b64decode(signature_b64)
    except Exception as exc:
        raise SnsVerificationError("invalid Signature encoding") from exc

    canonical = _canonical_string(envelope)

    hash_algo = hashes.SHA256() if signature_version == "2" else hashes.SHA1()  # noqa: S303  # legacy v1 SNS

    try:
        public_key.verify(signature, canonical, padding.PKCS1v15(), hash_algo)
    except InvalidSignature as exc:
        raise SnsVerificationError("signature mismatch") from exc
