"""Config directory location plus secure/tolerant JSON file helpers."""

import json
import os
import stat
from pathlib import Path

from . import constants


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(str(Path.home()), ".config")
    return Path(base) / constants.APP_DIR_NAME


def _write_secret_json(path: Path, data) -> None:
    """Write JSON with owner-only permissions (dir 0700, file 0600)."""
    directory = config_dir()
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, stat.S_IRWXU)
    fd = os.open(str(path), os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(data, handle)
    os.chmod(path, 0o600)


# Sentinel returned by _read_json_raw when a file exists but cannot be parsed,
# so callers can tell "missing" (None) apart from "present but corrupt".
_CORRUPT = object()


def _read_json_raw(path: Path):
    """Parse JSON at ``path``.

    Returns ``None`` if the file is absent, the ``_CORRUPT`` sentinel if it
    exists but cannot be read/parsed, and the decoded value otherwise.
    """
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return _CORRUPT


def _read_json(path: Path):
    """Tolerant JSON read: ``None`` for both a missing and a corrupt file."""
    data = _read_json_raw(path)
    return None if data is _CORRUPT else data
