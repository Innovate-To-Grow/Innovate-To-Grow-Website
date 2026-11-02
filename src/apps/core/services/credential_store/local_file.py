"""Local-development credential store: one 0600 JSON file per version in a 0700 directory under ``src/data/``.

For throwaway development keys only: production refuses this backend (``CREDENTIAL_STORE_REQUIRE_SECRETS_MANAGER``
and the core system check). Writes go to a temporary file that is renamed into place, so a reader never sees half a
key. The lock is per process; development has a single writer (the admin), and versions are never rewritten.
"""

import errno
import hashlib
import json
import os
import re
import threading
import uuid
from pathlib import Path

from django.conf import settings
from django.views.decorators.debug import sensitive_variables

from .base import CredentialStoreError
from .versioned import VersionedStore

DIRECTORY_MODE = 0o700
FILE_MODE = 0o600
STAGES_FILE = "stages.json"
UNUSABLE = "The local credential store could not be used."
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_lock = threading.RLock()


def _guarded(operation, *args):
    """Run one filesystem step; an OSError becomes fixed text plus its errno name, with no exception chain."""
    try:
        return operation(*args)
    except OSError as exc:
        code = errno.errorcode.get(exc.errno or 0, "")
    raise CredentialStoreError(UNUSABLE, code=code) from None


def _make_private_directory(path: Path) -> None:
    path.mkdir(mode=DIRECTORY_MODE, parents=True, exist_ok=True)
    os.chmod(path, DIRECTORY_MODE)


@sensitive_variables()
def _read_text(path: Path) -> str | None:
    try:
        descriptor = os.open(path, os.O_RDONLY | _NOFOLLOW)
    except FileNotFoundError:
        return None
    with os.fdopen(descriptor, encoding="utf-8") as handle:
        return handle.read()


@sensitive_variables()
def _write_text(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW, FILE_MODE)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), FILE_MODE)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _version_ids(directory: Path) -> list[str]:
    if not directory.is_dir():
        return []
    return sorted(path.stem for path in directory.glob("*.json") if path.name != STAGES_FILE)


def _parse_stages(text: str | None) -> dict[str, list[str]]:
    try:
        stages = json.loads(text) if text else {}
    except ValueError:
        stages = None
    valid = isinstance(stages, dict) and all(
        isinstance(labels, list) and all(isinstance(label, str) for label in labels) for labels in stages.values()
    )
    if not valid:
        raise CredentialStoreError(UNUSABLE, code="CorruptStages")
    return stages


class LocalFileStore(VersionedStore):
    scheme = "local-file"

    def __init__(self, root=None):
        self.root = Path(root if root is not None else settings.CREDENTIAL_STORE_LOCAL_DIR)

    def _lock(self, secret_id):
        return _lock

    def _directory(self, secret_id: str, *, create: bool) -> Path:
        # Readable and collision-free: "/" cannot appear in one path segment, so the digest keeps names apart.
        readable = re.sub(r"[^A-Za-z0-9_.-]", "_", secret_id)
        digest = hashlib.sha256(secret_id.encode()).hexdigest()[:12]
        directory = self.root / f"{readable}-{digest}"
        if create:
            _guarded(_make_private_directory, self.root)
            _guarded(_make_private_directory, directory)
        return directory

    def _read_version(self, secret_id, version_id):
        return _guarded(_read_text, self._directory(secret_id, create=False) / f"{version_id}.json")

    def _write_version(self, secret_id, version_id, text):
        _guarded(_write_text, self._directory(secret_id, create=True) / f"{version_id}.json", text)

    def _read_stages(self, secret_id):
        directory = self._directory(secret_id, create=False)
        labels = _parse_stages(_guarded(_read_text, directory / STAGES_FILE))
        return {version: list(labels.get(version, [])) for version in _guarded(_version_ids, directory)}

    def _write_stages(self, secret_id, stages):
        text = json.dumps(stages, sort_keys=True, indent=2)
        _guarded(_write_text, self._directory(secret_id, create=True) / STAGES_FILE, text)
