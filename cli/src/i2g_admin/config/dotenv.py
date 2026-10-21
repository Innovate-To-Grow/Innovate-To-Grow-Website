"""Project-owned ``.env`` loading.

Only the CLI's own ``.env`` (next to the project, never the caller's working
directory) is read, and only CLI-owned keys are imported from it.
"""

import os
from pathlib import Path

from . import constants


def _package_root() -> Path:
    """The cli/ directory: dotenv.py -> config -> i2g_admin -> src -> cli."""
    return Path(__file__).resolve().parent.parent.parent.parent


def _dotenv_paths() -> list[Path]:
    """Return the project-owned development .env path.

    The process working directory is intentionally excluded: invoking the CLI
    inside an untrusted checkout must not import that checkout's environment.
    """
    return [_package_root() / constants.DOTENV_FILE]


def _parse_dotenv(text: str) -> dict[str, str]:
    """Parse ``KEY=value`` lines; ignore blanks/``#`` comments; strip optional quotes."""
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key in constants.DOTENV_ALLOWED_KEYS:
            values[key] = value.strip().strip('"').strip("'")
    return values


def load_dotenv() -> None:
    """Populate CLI-owned environment keys from the project .env file.

    A value already present in the process environment always wins. Keys such
    as XDG_CONFIG_HOME, proxy settings, and CA bundle paths are never imported
    from a dotenv file.
    """
    for path in _dotenv_paths():
        if not path.is_file():
            continue
        for key, value in _parse_dotenv(path.read_text()).items():
            os.environ.setdefault(key, value)
