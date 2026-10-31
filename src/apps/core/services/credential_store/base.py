"""Shared contract of the credential stores: errors, version references, and the name / token / payload rules.

Error messages are fixed text plus, at most, the provider's error code. They never include a payload, a parameter
value or a provider message, because those can echo the key (botocore's ParamValidationError prints SecretString).
"""

import json
import re
import uuid
from dataclasses import dataclass

from django.conf import settings
from django.views.decorators.debug import sensitive_variables

from ..aws.secret_store import APPLICATION_ARN_PATTERN

CURRENT_STAGE = "AWSCURRENT"
PREVIOUS_STAGE = "AWSPREVIOUS"

# Secrets Manager's ClientRequestToken / VersionId bounds; our tokens are UUIDs.
_VERSION_ID_RE = re.compile(r"[A-Za-z0-9-]{32,64}")
# Secrets Manager's secret-name alphabet. The first character is alphanumeric, so no name is "." or "..".
_SECRET_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9/_+=.@-]{0,511}")
_STAGE_RE = re.compile(r"[A-Za-z0-9_.-]{1,256}")
_CODE_RE = re.compile(r"[A-Za-z0-9.]{1,64}")
_VERSION_NAMESPACE = "i2g.credential-store"

INVALID_NAME = "This credential has no valid entry in CREDENTIAL_STORE_SECRETS."
INVALID_PAYLOAD = "The credential payload must be a non-empty JSON object."
INVALID_VERSION = "The credential version id is not valid."
OVERSIZED_PAYLOAD = "The credential payload is larger than the store accepts."
UNREADABLE_PAYLOAD = "The stored credential is not a JSON object."
FOREIGN_REFERENCE = "The credential reference does not belong to this store."
VERSION_CONFLICT = "A different value is already stored under this version token; nothing was stored."


class CredentialStoreError(Exception):
    """A store operation failed or was refused. Carries fixed text and, at most, the provider's error code."""

    transient = False

    def __init__(self, message: str, *, code: str = ""):
        self.code = code if isinstance(code, str) and _CODE_RE.fullmatch(code) else ""
        super().__init__(f"{message} ({self.code})" if self.code else message)


class TransientCredentialStoreError(CredentialStoreError):
    """Throttling, a provider outage or a timeout: the same call may succeed later."""

    transient = True


@dataclass(frozen=True)
class StoredVersion:
    """One stored payload: the secret's ARN (or a local locator) and its immutable version id."""

    arn: str
    version_id: str


@dataclass(frozen=True)
class SecretDescription:
    """The labelled versions of one secret. Labels are bookkeeping: the database pin decides which key is used."""

    arn: str
    version_stages: tuple[tuple[str, tuple[str, ...]], ...]

    def stages_of(self, version_id: str) -> tuple[str, ...]:
        return next((stages for version, stages in self.version_stages if version == version_id), ())

    @property
    def current_version_id(self) -> str:
        return next((version for version, stages in self.version_stages if CURRENT_STAGE in stages), "")


def staged_label() -> str:
    return settings.CREDENTIAL_STORE_STAGED_LABEL


def valid_staged_label(label) -> bool:
    return isinstance(label, str) and bool(_STAGE_RE.fullmatch(label)) and not label.upper().startswith("AWS")


def valid_secret_id(secret_id) -> bool:
    if not isinstance(secret_id, str) or not _SECRET_ID_RE.fullmatch(secret_id):
        return False
    # The AWS credential resolver reads its own namespace; a key kept here must never be reachable through it.
    sample_arn = (
        f"arn:aws:secretsmanager:{settings.CREDENTIAL_STORE_AWS_REGION}:"
        f"{settings.CREDENTIAL_STORE_AWS_ACCOUNT_ID}:secret:{secret_id}-AbCdEf"
    )
    return not re.fullmatch(APPLICATION_ARN_PATTERN, sample_arn)


def secret_id_for(name: str) -> str:
    """The configured secret name for a logical credential name; anything not listed in settings is refused."""
    secrets = settings.CREDENTIAL_STORE_SECRETS
    secret_id = secrets.get(name) if isinstance(secrets, dict) and isinstance(name, str) else None
    if not valid_secret_id(secret_id):
        raise CredentialStoreError(INVALID_NAME)
    return secret_id


def version_token_for(name: str, fingerprint: str) -> str:
    """A deterministic version token, so storing the same key twice is a no-op instead of a second version."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{_VERSION_NAMESPACE}:{name}:{fingerprint}"))


def validate_version_id(version_id) -> str:
    if not isinstance(version_id, str) or not _VERSION_ID_RE.fullmatch(version_id):
        raise CredentialStoreError(INVALID_VERSION)
    return version_id


@sensitive_variables()
def serialize_payload(payload) -> str:
    """Canonical JSON (sorted keys, no spaces), so one payload always produces the same bytes."""
    text = None
    if isinstance(payload, dict) and payload and all(isinstance(key, str) for key in payload):
        try:
            text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
        except (TypeError, ValueError):
            text = None
    if text is None:
        raise CredentialStoreError(INVALID_PAYLOAD)
    if len(text.encode("ascii")) > settings.CREDENTIAL_STORE_MAX_PAYLOAD_BYTES:
        raise CredentialStoreError(OVERSIZED_PAYLOAD)
    return text


@sensitive_variables()
def parse_payload(text) -> dict:
    payload = None
    if isinstance(text, str):
        try:
            payload = json.loads(text)
        except ValueError:
            payload = None
    if not isinstance(payload, dict) or not payload:
        raise CredentialStoreError(UNREADABLE_PAYLOAD)
    return payload
