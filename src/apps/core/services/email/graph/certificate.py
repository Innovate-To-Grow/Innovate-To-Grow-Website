"""Entra certificate credentials: check the PEM pair and sign client assertions (``private_key_jwt``).

Microsoft documents the assertion format in "Microsoft identity platform certificate credentials": a PS256 JWT
whose header carries ``x5t#S256`` (the base64url SHA-256 thumbprint of the certificate's DER encoding) and whose
claims name the tenant token endpoint as ``aud`` and the application ID as ``iss`` and ``sub``.
"""

import base64
import hashlib
import time
import uuid
from dataclasses import dataclass
from datetime import datetime

import jwt
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

# Microsoft: keep the assertion short-lived, "5-10 minutes after nbf at most".
ASSERTION_LIFETIME_SECONDS = 300
MIN_RSA_KEY_BITS = 2048
TOKEN_ENDPOINT = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"  # nosec B105 — URL template, not a credential


class CertificateError(ValueError):
    """The certificate or private key cannot be used. Messages never contain key material."""


@dataclass(frozen=True)
class CertificateInfo:
    thumbprint: str
    not_before: datetime
    not_after: datetime
    subject: str


def inspect_pair(certificate_pem: str, private_key_pem: str) -> CertificateInfo:
    """Validate that the RSA private key belongs to the certificate and describe the certificate."""
    certificate = _load_certificate(certificate_pem)
    public_key = certificate.public_key()
    if not isinstance(public_key, rsa.RSAPublicKey):
        raise CertificateError("Entra certificate credentials must use an RSA key.")
    if public_key.key_size < MIN_RSA_KEY_BITS:
        raise CertificateError(f"The certificate key must be at least {MIN_RSA_KEY_BITS} bits.")
    private_key = load_private_key(private_key_pem)
    if private_key.public_key().public_numbers() != public_key.public_numbers():
        raise CertificateError("The private key does not belong to this certificate.")
    return CertificateInfo(
        thumbprint=_thumbprint(certificate),
        not_before=certificate.not_valid_before_utc,
        not_after=certificate.not_valid_after_utc,
        subject=certificate.subject.rfc4514_string(),
    )


def load_private_key(private_key_pem: str) -> rsa.RSAPrivateKey:
    try:
        key = serialization.load_pem_private_key((private_key_pem or "").strip().encode("ascii"), password=None)
    except TypeError as exc:
        raise CertificateError("The private key must not be password-protected (export it unencrypted).") from exc
    except (ValueError, UnicodeError) as exc:
        raise CertificateError("The private key is not a readable PEM private key.") from exc
    if not isinstance(key, rsa.RSAPrivateKey):
        raise CertificateError("Entra certificate credentials must use an RSA key.")
    return key


def build_client_assertion(*, tenant_id: str, client_id: str, private_key_pem: str, thumbprint: str) -> str:
    """A signed JWT that proves possession of the certificate's private key to the identity platform."""
    now = int(time.time())
    claims = {
        "aud": TOKEN_ENDPOINT.format(tenant=tenant_id),
        "iss": client_id,
        "sub": client_id,
        "jti": str(uuid.uuid4()),
        "nbf": now,
        "iat": now,
        "exp": now + ASSERTION_LIFETIME_SECONDS,
    }
    headers = {"typ": "JWT", "x5t#S256": thumbprint}
    return jwt.encode(claims, load_private_key(private_key_pem), algorithm="PS256", headers=headers)


def _load_certificate(certificate_pem: str) -> x509.Certificate:
    try:
        return x509.load_pem_x509_certificate((certificate_pem or "").strip().encode("ascii"))
    except (ValueError, UnicodeError) as exc:
        raise CertificateError("The certificate is not a readable PEM certificate.") from exc


def _thumbprint(certificate: x509.Certificate) -> str:
    digest = hashlib.sha256(certificate.public_bytes(serialization.Encoding.DER)).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
