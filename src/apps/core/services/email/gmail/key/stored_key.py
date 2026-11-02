"""The Gmail API service-account key in the credential store: its payload, and verified reads of a pinned version.

One store version holds one key, as the canonical subset of the key file: ``type``, ``client_email``,
``client_id``, ``private_key_id``, ``private_key`` and ``project_id`` (never ``token_uri`` or the other URLs). The
version token is derived from the key id and public key, so storing the same key again is a no-op. A read names the
exact version the config pins, and the key it returns must match the config's recorded facts. Nothing caches a key.
"""

import hashlib

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.views.decorators.debug import sensitive_variables

from apps.core.services.credential_store import CredentialStoreError, StoredVersion, get_store, version_token_for

from ..assertion import SigningKeyError, load_signing_key

KEY_NAME = "gmail_api_service_account_key"
PAYLOAD_FIELDS = ("type", "client_email", "client_id", "private_key_id", "private_key", "project_id")
SERVICE_ACCOUNT_TYPE = "service_account"


class StoredKeyMismatch(CredentialStoreError):
    """The pinned version is not the installed key (other facts, or not a usable key at all)."""

    def __init__(self):
        super().__init__("The stored Gmail API key does not match the installed key facts.")


def public_key_sha256(private_key: rsa.RSAPrivateKey) -> str:
    spki = private_key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return hashlib.sha256(spki).hexdigest()


@sensitive_variables()
def store_key(payload: dict, private_key: rsa.RSAPrivateKey) -> StoredVersion:
    """Add the canonical *payload* as a new (staged) version, or find the version that already holds it."""
    canonical = {field: payload[field] for field in PAYLOAD_FIELDS}
    token = version_token_for(KEY_NAME, f"{canonical['private_key_id']}:{public_key_sha256(private_key)}")
    return get_store().put(KEY_NAME, canonical, version_token=token)


@sensitive_variables()
def read_key(*, arn: str, version_id: str, client_email: str, key_id: str) -> rsa.RSAPrivateKey:
    """The signing key in exactly this version, checked against the service account and key id the config records.

    Raises ``CredentialStoreError`` (``TransientCredentialStoreError`` when a retry may help); a payload that is not
    the installed key raises ``StoredKeyMismatch``.
    """
    payload = get_store().read(KEY_NAME, arn=arn, version_id=version_id)
    matches = (
        payload.get("type") == SERVICE_ACCOUNT_TYPE
        and bool(client_email)
        and payload.get("client_email") == client_email
        and bool(key_id)
        and payload.get("private_key_id") == key_id
    )
    if not matches:
        raise StoredKeyMismatch()
    try:
        return load_signing_key(payload.get("private_key"))
    except SigningKeyError:
        raise StoredKeyMismatch() from None
