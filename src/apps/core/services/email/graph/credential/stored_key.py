"""The Graph certificate's private key in the credential store: its payload, and verified reads of a pinned version.

One store version holds one key, as canonical unencrypted PKCS#8 plus the SHA-256 of its public key. The version
token is derived from that hash, so storing the same key again (from PEM, PKCS#1, an encrypted PEM or a .p12) is a
no-op. A read names the exact version a ``MicrosoftGraphCertificate`` row pins, and the key it returns must match
that row's public key. Nothing here caches a key.
"""

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.views.decorators.debug import sensitive_variables

from apps.core.services.credential_store import CredentialStoreError, StoredVersion, get_store, version_token_for

from ..certificate import public_key_sha256

KEY_NAME = "microsoft_graph_certificate_key"
PAYLOAD_SCHEMA = "i2g.graph-key/1"


class StoredKeyMismatch(CredentialStoreError):
    """The pinned version is not the key of the installed certificate (or not a key at all)."""

    def __init__(self):
        super().__init__("The stored private key does not match the installed certificate.")


@sensitive_variables()
def key_payload(private_key: rsa.RSAPrivateKey) -> dict:
    pem = private_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode("ascii")
    return {
        "schema": PAYLOAD_SCHEMA,
        "private_key_pem": pem,
        "public_key_sha256": public_key_sha256(private_key.public_key()),
    }


@sensitive_variables()
def store_key(private_key: rsa.RSAPrivateKey) -> StoredVersion:
    """Add the key as a new (staged) version, or find the version that already holds it."""
    payload = key_payload(private_key)
    token = version_token_for(KEY_NAME, payload["public_key_sha256"])
    return get_store().put(KEY_NAME, payload, version_token=token)


@sensitive_variables()
def read_key(*, arn: str, version_id: str, expected_public_key_sha256: str) -> rsa.RSAPrivateKey:
    """The private key in exactly this version, checked against the certificate's public key hash.

    Raises ``CredentialStoreError`` (``TransientCredentialStoreError`` when a retry may help); a payload that is
    not the expected key raises ``StoredKeyMismatch``.
    """
    payload = get_store().read(KEY_NAME, arn=arn, version_id=version_id)
    key = _load(payload)
    if (
        not expected_public_key_sha256
        or payload.get("public_key_sha256") != expected_public_key_sha256
        or public_key_sha256(key.public_key()) != expected_public_key_sha256
    ):
        raise StoredKeyMismatch()
    return key


@sensitive_variables()
def _load(payload: dict) -> rsa.RSAPrivateKey:
    pem = payload.get("private_key_pem")
    key = None
    if payload.get("schema") == PAYLOAD_SCHEMA and isinstance(pem, str):
        try:
            key = serialization.load_pem_private_key(pem.encode("ascii"), password=None)
        except (ValueError, TypeError, UnicodeError, UnsupportedAlgorithm):
            key = None
    if not isinstance(key, rsa.RSAPrivateKey):
        raise StoredKeyMismatch()
    return key
