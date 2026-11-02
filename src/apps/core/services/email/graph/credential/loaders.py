"""Load one certificate, one private key, or a .p12/.pfx bundle from what an admin uploaded or pasted.

Every failure is a ``CertificateInputError``: a fixed message on the input it concerns, never containing any part of
the input, and raised ``from None`` so no cryptography exception (or its arguments) travels with it.
"""

import base64
import binascii
import re

from cryptography import x509
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from django.views.decorators.debug import sensitive_variables

CERTIFICATE = "certificate"
PRIVATE_KEY = "private_key"
BUNDLE = "bundle"
PASSWORD = "password"  # nosec B105 — the name of the passphrase input, not a credential

UNREADABLE_CERTIFICATE = "The certificate could not be read. Use a PEM certificate, a DER .cer file, or base64."
KEY_IN_CERTIFICATE = (
    "The Certificate input contains a private key. Enter only the certificate there; "
    "the private key goes in the Private key input."
)
ONE_CERTIFICATE = "Enter exactly one certificate (the leaf certificate registered in Entra), not a chain or bundle."
UNREADABLE_KEY = "The private key could not be read. Use a PEM private key (PKCS#8 or PKCS#1)."
CERTIFICATE_IN_KEY = "The Private key input contains only a certificate. Enter the private key there."
ONE_KEY = "The Private key input must contain one private key and, at most, its certificate."
RSA_ONLY = "Entra certificate credentials must use an RSA key."
KEY_NEEDS_PASSPHRASE = "This private key is encrypted. Enter its passphrase."  # nosec B105 — validation message
WRONG_PASSPHRASE = "The passphrase does not open this private key."  # nosec B105 — validation message
UNOPENED_BUNDLE = "The .p12/.pfx file could not be opened with this password. Check the file and its password."
INCOMPLETE_BUNDLE = "The .p12/.pfx file must contain both the certificate and its private key."
NOT_TEXT = "This input must be text (ASCII)."

_BEGIN_RE = re.compile(rb"-----BEGIN ([A-Z0-9 ]{1,64})-----")
_BOM = b"\xef\xbb\xbf"
_DER_SEQUENCE = 0x30


class CertificateInputError(ValueError):
    """An admin input cannot be used. ``field`` names the input; the message is fixed text."""

    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field
        self.message = message


def as_bytes(value, field: str) -> bytes:
    """Pasted text (str) or an uploaded file's content (bytes), without a UTF-8 byte-order mark."""
    if isinstance(value, str):
        try:
            value = value.encode("ascii")
        except UnicodeError:
            raise CertificateInputError(field, NOT_TEXT) from None
    data = bytes(value or b"")
    return data[len(_BOM) :] if data.startswith(_BOM) else data


def pem_labels(data: bytes) -> list[str]:
    return [label.decode("ascii") for label in _BEGIN_RE.findall(data)]


def load_certificate(data: bytes) -> x509.Certificate:
    """One certificate as PEM (one block), DER (a .cer file), or header-less base64 of the DER."""
    if b"PRIVATE KEY" in data:
        raise CertificateInputError(CERTIFICATE, KEY_IN_CERTIFICATE)
    labels = pem_labels(data)
    if labels and labels != ["CERTIFICATE"]:
        raise CertificateInputError(CERTIFICATE, ONE_CERTIFICATE)
    try:
        if labels:
            return x509.load_pem_x509_certificate(data)
        if data[:1] == bytes([_DER_SEQUENCE]):
            # Binary DER is read untrimmed: its signature can end in a byte that strip() takes for whitespace.
            return x509.load_der_x509_certificate(data)
        return x509.load_der_x509_certificate(base64.b64decode(b"".join(data.split()), validate=True))
    except (ValueError, TypeError, binascii.Error, UnsupportedAlgorithm):
        raise CertificateInputError(CERTIFICATE, UNREADABLE_CERTIFICATE) from None


@sensitive_variables()
def load_private_key(data: bytes, password: str) -> tuple[rsa.RSAPrivateKey, x509.Certificate | None]:
    """The RSA private key, plus the certificate when the input is a combined key + certificate PEM."""
    labels = pem_labels(data)
    if not labels:
        return _rsa(_decrypt(serialization.load_der_private_key, data, password)), None
    key_labels = [label for label in labels if label.endswith("PRIVATE KEY")]
    certificate_labels = [label for label in labels if label == "CERTIFICATE"]
    if "EC PRIVATE KEY" in key_labels or "EC PARAMETERS" in labels:
        raise CertificateInputError(PRIVATE_KEY, RSA_ONLY)
    if not key_labels:
        raise CertificateInputError(PRIVATE_KEY, CERTIFICATE_IN_KEY if certificate_labels else UNREADABLE_KEY)
    if len(key_labels) > 1 or len(certificate_labels) > 1 or len(labels) != len(key_labels) + len(certificate_labels):
        raise CertificateInputError(PRIVATE_KEY, ONE_KEY)
    key = _rsa(_decrypt(serialization.load_pem_private_key, data, password))
    if not certificate_labels:
        return key, None
    try:
        return key, x509.load_pem_x509_certificate(data)
    except (ValueError, TypeError, UnsupportedAlgorithm):
        raise CertificateInputError(PRIVATE_KEY, UNREADABLE_CERTIFICATE) from None


@sensitive_variables()
def load_bundle(data: bytes, password: str) -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    """The key and leaf certificate of a .p12/.pfx file (as macOS Keychain exports). CA certificates are ignored."""
    try:
        key, certificate, _chain = pkcs12.load_key_and_certificates(data, _secret(password))
    except (ValueError, TypeError, UnsupportedAlgorithm):
        raise CertificateInputError(PASSWORD, UNOPENED_BUNDLE) from None
    if key is None or certificate is None:
        raise CertificateInputError(BUNDLE, INCOMPLETE_BUNDLE)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise CertificateInputError(BUNDLE, RSA_ONLY)
    return key, certificate


@sensitive_variables()
def _decrypt(loader, data: bytes, password: str):
    """Load an unencrypted key, or decrypt an encrypted one with *password* (ignored for an unencrypted key)."""
    try:
        return loader(data, password=None)
    except TypeError:
        pass  # the key is encrypted (cryptography's signal for "a password is needed")
    except UnsupportedAlgorithm:
        raise CertificateInputError(PRIVATE_KEY, RSA_ONLY) from None
    except ValueError:
        raise CertificateInputError(PRIVATE_KEY, UNREADABLE_KEY) from None
    if not password:
        raise CertificateInputError(PASSWORD, KEY_NEEDS_PASSPHRASE)
    try:
        return loader(data, password=_secret(password))
    except (TypeError, ValueError, UnsupportedAlgorithm):
        raise CertificateInputError(PASSWORD, WRONG_PASSPHRASE) from None


def _secret(password: str) -> bytes | None:
    return password.encode("utf-8") if password else None


def _rsa(key) -> rsa.RSAPrivateKey:
    if not isinstance(key, rsa.RSAPrivateKey):
        raise CertificateInputError(PRIVATE_KEY, RSA_ONLY)
    return key
