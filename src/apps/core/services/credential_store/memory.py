"""Process-memory credential store for tests. Shared by every store instance in the process; ``reset()`` empties it."""

import copy
import threading

from .versioned import VersionedStore

_lock = threading.RLock()
_versions: dict[str, dict[str, str]] = {}
_stages: dict[str, dict[str, list[str]]] = {}


def reset() -> None:
    with _lock:
        _versions.clear()
        _stages.clear()


class MemoryStore(VersionedStore):
    scheme = "memory"

    def _lock(self, secret_id):
        return _lock

    def _read_version(self, secret_id, version_id):
        return _versions.get(secret_id, {}).get(version_id)

    def _write_version(self, secret_id, version_id, text):
        _versions.setdefault(secret_id, {})[version_id] = text

    def _read_stages(self, secret_id):
        return copy.deepcopy(_stages.get(secret_id, {}))

    def _write_stages(self, secret_id, stages):
        _stages[secret_id] = copy.deepcopy(stages)
