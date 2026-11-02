"""Entra certificate credentials: describe a certificate and sign client assertions (``private_key_jwt``).

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
from django.conf import settings

TOKEN_ENDPOINT = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"  # nosec B105 — URL template, not a credential


@dataclass(frozen=True)
class CertificateFacts:
    """The public data of one certificate, as ``MicrosoftGraphCertificate`` stores it.

    ``sha1_thumbprint`` is the upper-case hex value Entra shows under Certificates & secrets (and the value OIT
    quotes); ``x5t_s256`` is the base64url SHA-256 thumbprint the assertion header carries.
    """

    certificate_pem: str
    sha1_thumbprint: str
    sha256_fingerprint: str
    x5t_s256: str
    public_key_sha256: str
    subject: str
    issuer: str
    serial_number: str
    key_bits: int
    not_before: datetime
    not_after: datetime


def describe_certificate(certificate: x509.Certificate) -> CertificateFacts:
    """Re-serialise the leaf certificate and compute its thumbprints. The caller has checked it holds an RSA key."""
    der = certificate.public_bytes(serialization.Encoding.DER)
    public_key = certificate.public_key()
    return CertificateFacts(
        certificate_pem=certificate.public_bytes(serialization.Encoding.PEM).decode("ascii"),
        # SHA-1 only identifies the certificate the way Entra displays it; nothing is verified with it.
        sha1_thumbprint=hashlib.sha1(der, usedforsecurity=False).hexdigest().upper(),
        sha256_fingerprint=hashlib.sha256(der).hexdigest().upper(),
        x5t_s256=base64.urlsafe_b64encode(hashlib.sha256(der).digest()).rstrip(b"=").decode("ascii"),
        public_key_sha256=public_key_sha256(public_key),
        subject=certificate.subject.rfc4514_string(),
        issuer=certificate.issuer.rfc4514_string(),
        serial_number=format(certificate.serial_number, "X"),
        key_bits=public_key.key_size,
        not_before=certificate.not_valid_before_utc,
        not_after=certificate.not_valid_after_utc,
    )


def public_key_sha256(public_key) -> str:
    """Hex SHA-256 of the DER SubjectPublicKeyInfo: ties a stored private key to the certificate it belongs to."""
    spki = public_key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return hashlib.sha256(spki).hexdigest()


def build_client_assertion(*, tenant_id: str, client_id: str, private_key: rsa.RSAPrivateKey, x5t_s256: str) -> str:
    """A signed JWT that proves possession of the certificate's private key to the identity platform."""
    now = int(time.time())
    claims = {
        "aud": TOKEN_ENDPOINT.format(tenant=tenant_id),
        "iss": client_id,
        "sub": client_id,
        "jti": str(uuid.uuid4()),
        "nbf": now,
        "iat": now,
        "exp": now + settings.GRAPH_CLIENT_ASSERTION_LIFETIME_SECONDS,
    }
    headers = {"typ": "JWT", "x5t#S256": x5t_s256}
    return jwt.encode(claims, private_key, algorithm="PS256", headers=headers)
