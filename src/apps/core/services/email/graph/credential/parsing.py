"""Read a Microsoft Graph certificate and its private key as an admin enters them, entirely in memory.

Accepted inputs:
- a .p12/.pfx bundle and its password (what macOS Keychain exports); or
- a certificate as PEM, a DER .cer file or header-less base64, plus an RSA private key as PEM PKCS#8 / PKCS#1
  (optionally encrypted, with its passphrase). A combined key + certificate PEM is accepted in the private-key
  input only; a certificate input that contains a private key is refused.
- the certificate alone, when it re-issues the installed key (the lifecycle checks the public key matches).

The result carries the re-serialised leaf certificate, its thumbprints and the loaded key object. Errors are
``CertificateInputError`` with a fixed message on the input they concern; none contains any part of the input.
"""

from dataclasses import dataclass, field
from datetime import timedelta

from cryptography import x509
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from ..certificate import CertificateFacts, describe_certificate
from .loaders import (
    BUNDLE,
    CERTIFICATE,
    PASSWORD,
    PRIVATE_KEY,
    RSA_ONLY,
    UNREADABLE_CERTIFICATE,
    CertificateInputError,
    as_bytes,
    load_bundle,
    load_certificate,
    load_private_key,
)

CERTIFICATE_REQUIRED = "Enter the certificate, or upload a .p12/.pfx file that contains it."
BUNDLE_OR_PARTS = "Upload a .p12/.pfx file or enter the certificate and private key, not both."
DIFFERENT_CERTIFICATES = "The Private key input contains a different certificate than the Certificate input."
KEY_MISMATCH = "The private key does not belong to this certificate."
EXPIRED = "This certificate has expired. Create a new one, register it in Entra, and install that."
NOT_YET_VALID = "This certificate is not valid yet. Entra refuses it until its start date."
TOO_LARGE = "This input is larger than a certificate or key can be."
# MicrosoftGraphCertificate.serial_number's column width (RFC 5280 allows 20 octets, i.e. 40 hex digits).
MAX_SERIAL_LENGTH = 128

PKCS12 = "pkcs12"
PEM_OR_DER = "pem"


@dataclass(frozen=True)
class ParsedCertificate:
    """A validated certificate and, unless it re-issues the installed key, its RSA private key (never in repr)."""

    facts: CertificateFacts
    private_key: rsa.RSAPrivateKey | None = field(default=None, repr=False)
    source_format: str = PEM_OR_DER


@sensitive_variables()
def parse_certificate_input(*, certificate=b"", private_key=b"", bundle=b"", password="") -> ParsedCertificate:
    """Each input is pasted text (str) or an uploaded file's bytes; blank inputs are ignored."""
    raw = {CERTIFICATE: certificate, PRIVATE_KEY: private_key, BUNDLE: bundle}
    inputs = {name: as_bytes(value, name) for name, value in raw.items()}
    for name, data in inputs.items():
        if len(data) > settings.GRAPH_CERTIFICATE_MAX_INPUT_BYTES:
            raise CertificateInputError(name, TOO_LARGE)
    if inputs[BUNDLE].strip():
        if inputs[CERTIFICATE].strip() or inputs[PRIVATE_KEY].strip():
            raise CertificateInputError(BUNDLE, BUNDLE_OR_PARTS)
        key, leaf = load_bundle(inputs[BUNDLE], password or "")
        return _validated(leaf, key, certificate_field=BUNDLE, source_format=PKCS12)
    key, leaf = _parts(inputs[CERTIFICATE], inputs[PRIVATE_KEY], password or "")
    return _validated(leaf, key, certificate_field=CERTIFICATE, source_format=PEM_OR_DER)


@sensitive_variables()
def _parts(certificate_data: bytes, key_data: bytes, password: str):
    key, certificate_in_key = load_private_key(key_data, password) if key_data.strip() else (None, None)
    leaf = load_certificate(certificate_data) if certificate_data.strip() else certificate_in_key
    if leaf is None:
        raise CertificateInputError(CERTIFICATE, CERTIFICATE_REQUIRED)
    if certificate_in_key is not None and certificate_in_key != leaf:
        raise CertificateInputError(PRIVATE_KEY, DIFFERENT_CERTIFICATES)
    return key, leaf


@sensitive_variables()
def _validated(leaf: x509.Certificate, key, *, certificate_field: str, source_format: str) -> ParsedCertificate:
    facts = _facts(leaf, certificate_field)
    now = timezone.now()
    if facts.not_after <= now:
        raise CertificateInputError(certificate_field, EXPIRED)
    if facts.not_before > now + timedelta(seconds=settings.GRAPH_CERTIFICATE_CLOCK_SKEW_SECONDS):
        raise CertificateInputError(certificate_field, NOT_YET_VALID)
    if key is not None and key.public_key().public_numbers() != leaf.public_key().public_numbers():
        raise CertificateInputError(PRIVATE_KEY if certificate_field == CERTIFICATE else BUNDLE, KEY_MISMATCH)
    return ParsedCertificate(facts=facts, private_key=key, source_format=source_format)


def _facts(leaf: x509.Certificate, certificate_field: str) -> CertificateFacts:
    try:
        public_key = leaf.public_key()
    except (ValueError, UnsupportedAlgorithm):
        raise CertificateInputError(certificate_field, RSA_ONLY) from None
    if not isinstance(public_key, rsa.RSAPublicKey):
        raise CertificateInputError(certificate_field, RSA_ONLY)
    minimum = settings.GRAPH_CERTIFICATE_MIN_RSA_KEY_BITS
    if public_key.key_size < minimum:
        raise CertificateInputError(certificate_field, f"The certificate's RSA key must be at least {minimum} bits.")
    try:
        facts = describe_certificate(leaf)
    except (ValueError, UnsupportedAlgorithm):
        raise CertificateInputError(certificate_field, UNREADABLE_CERTIFICATE) from None
    if len(facts.serial_number) > MAX_SERIAL_LENGTH:
        raise CertificateInputError(certificate_field, UNREADABLE_CERTIFICATE)
    return facts


__all__ = [
    "BUNDLE",
    "CERTIFICATE",
    "PASSWORD",
    "PRIVATE_KEY",
    "CertificateInputError",
    "ParsedCertificate",
    "parse_certificate_input",
]
