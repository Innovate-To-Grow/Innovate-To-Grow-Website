"""Secrets Manager's version and label rules for the stores this process keeps itself (local file and memory).

Both follow the same contract as the Secrets Manager backend, so code written against one behaves the same on all:

- A version is immutable. Re-sending the same token with the same payload is a no-op; a different payload fails.
- A new version gets the staged label. Only the very first version of a secret also becomes ``AWSCURRENT``.
- Moving ``AWSCURRENT`` hands ``AWSPREVIOUS`` to the version it left.
- Every read names its version: nothing ever reads "whatever is current".
"""

import logging

from django.views.decorators.debug import sensitive_variables

from .base import (
    CURRENT_STAGE,
    FOREIGN_REFERENCE,
    PREVIOUS_STAGE,
    VERSION_CONFLICT,
    CredentialStoreError,
    SecretDescription,
    StoredVersion,
    parse_payload,
    secret_id_for,
    serialize_payload,
    staged_label,
    validate_version_id,
)

logger = logging.getLogger(__name__)

NOT_FOUND = "The credential could not be read from the credential store."


class VersionedStore:
    """Subclasses keep the bytes; this class applies the version and label rules under the subclass's lock."""

    scheme = ""

    # Storage primitives -------------------------------------------------------------------------------------------
    def _lock(self, secret_id):
        raise NotImplementedError

    def _read_version(self, secret_id: str, version_id: str) -> str | None:
        raise NotImplementedError

    def _write_version(self, secret_id: str, version_id: str, text: str) -> None:
        raise NotImplementedError

    def _read_stages(self, secret_id: str) -> dict[str, list[str]]:
        """Every stored version id mapped to its labels (an empty list for an unlabelled version)."""
        raise NotImplementedError

    def _write_stages(self, secret_id: str, stages: dict[str, list[str]]) -> None:
        raise NotImplementedError

    # Public operations --------------------------------------------------------------------------------------------
    def arn_for(self, secret_id: str) -> str:
        return f"{self.scheme}:{secret_id}"

    @sensitive_variables()
    def put(self, name: str, payload: dict, *, version_token: str) -> StoredVersion:
        secret_id = secret_id_for(name)
        text = serialize_payload(payload)
        validate_version_id(version_token)
        label = staged_label()
        with self._lock(secret_id):
            existing = self._read_version(secret_id, version_token)
            if existing is not None and existing != text:
                raise CredentialStoreError(VERSION_CONFLICT)
            if existing is None:
                stages = self._read_stages(secret_id)
                first = not stages
                self._write_version(secret_id, version_token, text)
                stages = {version: [s for s in labels if s != label] for version, labels in stages.items()}
                stages[version_token] = [label, CURRENT_STAGE] if first else [label]
                self._write_stages(secret_id, stages)
        return StoredVersion(arn=self.arn_for(secret_id), version_id=version_token)

    @sensitive_variables()
    def read(self, name: str, *, arn: str, version_id: str) -> dict:
        secret_id = secret_id_for(name)
        if arn != self.arn_for(secret_id):
            raise CredentialStoreError(FOREIGN_REFERENCE)
        validate_version_id(version_id)
        with self._lock(secret_id):
            text = self._read_version(secret_id, version_id)
        if text is None:
            raise CredentialStoreError(NOT_FOUND, code="ResourceNotFoundException")
        return parse_payload(text)

    def describe(self, name: str) -> SecretDescription:
        secret_id = secret_id_for(name)
        with self._lock(secret_id):
            stages = self._read_stages(secret_id)
        labelled = tuple((version, tuple(labels)) for version, labels in sorted(stages.items()) if labels)
        return SecretDescription(arn=self.arn_for(secret_id), version_stages=labelled)

    def move_current(self, name: str, version_id: str) -> bool:
        """Best effort: label ``version_id`` as current. An unknown version is logged and returns False."""
        secret_id = secret_id_for(name)
        validate_version_id(version_id)
        with self._lock(secret_id):
            stages = self._read_stages(secret_id)
            if version_id not in stages:
                logger.warning("Credential store label update skipped for %s: the version is not stored.", name)
                return False
            holder = next((version for version, labels in stages.items() if CURRENT_STAGE in labels), "")
            if holder == version_id:
                return True
            for version, labels in stages.items():
                stages[version] = [s for s in labels if s not in (CURRENT_STAGE, PREVIOUS_STAGE)]
                if version == holder:
                    stages[version].append(PREVIOUS_STAGE)
            stages[version_id].append(CURRENT_STAGE)
            self._write_stages(secret_id, stages)
        return True
