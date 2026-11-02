"""Versioned private-key store: AWS Secrets Manager in production, 0600 files locally, process memory in tests.

The database keeps only a pointer to a stored key (``StoredVersion``: ARN + version id), and every read names that
exact version. A logical name (a key of ``settings.CREDENTIAL_STORE_SECRETS``) selects the secret, so callers never
pass a free-form secret id. Every backend implements:

- ``put(name, payload, *, version_token)`` stores a new immutable version under the staged label, so the version
  Secrets Manager calls current never moves on a write. The same token and payload again is a no-op; build the
  token with ``version_token_for`` from a fingerprint of the key.
- ``read(name, *, arn, version_id)`` returns the payload of exactly that version.
- ``describe(name)`` lists the labelled versions; ``move_current(name, version_id)`` relabels, best effort.

Failures raise ``CredentialStoreError`` (``TransientCredentialStoreError`` when a retry may succeed) with fixed text
and the provider's error code only.
"""

from django.conf import settings

from .base import (
    CURRENT_STAGE,
    PREVIOUS_STAGE,
    CredentialStoreError,
    SecretDescription,
    StoredVersion,
    TransientCredentialStoreError,
    secret_id_for,
    valid_secret_id,
    valid_staged_label,
    version_token_for,
)
from .local_file import LocalFileStore
from .memory import MemoryStore
from .secrets_manager import SecretsManagerStore

SECRETS_MANAGER = "secretsmanager"
LOCAL_FILE = "local_file"
MEMORY = "memory"
BACKENDS = {SECRETS_MANAGER: SecretsManagerStore, LOCAL_FILE: LocalFileStore, MEMORY: MemoryStore}

REQUIRES_SECRETS_MANAGER = "This environment keeps private keys only in AWS Secrets Manager."
UNKNOWN_BACKEND = "CREDENTIAL_STORE_BACKEND names no credential store."


def get_store():
    """The configured store. Refuses anything but Secrets Manager where settings require it (production)."""
    backend = settings.CREDENTIAL_STORE_BACKEND
    if settings.CREDENTIAL_STORE_REQUIRE_SECRETS_MANAGER and backend != SECRETS_MANAGER:
        raise CredentialStoreError(REQUIRES_SECRETS_MANAGER)
    if backend not in BACKENDS:
        raise CredentialStoreError(UNKNOWN_BACKEND)
    return BACKENDS[backend]()


__all__ = [
    "BACKENDS",
    "CURRENT_STAGE",
    "LOCAL_FILE",
    "MEMORY",
    "PREVIOUS_STAGE",
    "SECRETS_MANAGER",
    "CredentialStoreError",
    "SecretDescription",
    "StoredVersion",
    "TransientCredentialStoreError",
    "get_store",
    "secret_id_for",
    "valid_secret_id",
    "valid_staged_label",
    "version_token_for",
]
