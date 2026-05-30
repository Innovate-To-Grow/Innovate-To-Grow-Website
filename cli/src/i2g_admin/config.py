import json
import os
from pathlib import Path
from urllib.parse import urlparse

from .errors import CliError

APP_DIR_NAME = "i2g-admin"
CREDENTIALS_FILE = "credentials.json"
DEFAULT_BASE_URL = "https://api.i2g.ucmerced.edu"
# http is only permitted to literal loopback hosts (local dev); everything else
# must be https so the bearer token is never sent in cleartext to a remote host.
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def validate_base_url(url: str) -> str:
    """Return the URL if it is https (any host) or http to a loopback host; else raise."""
    parsed = urlparse(url or "")
    if parsed.scheme == "https" and parsed.netloc:
        return url
    if parsed.scheme == "http" and parsed.hostname in LOOPBACK_HOSTS:
        return url
    raise CliError(f"base_url must be https, or http on a loopback host (got {url!r}).")


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(str(Path.home()), ".config")
    return Path(base) / APP_DIR_NAME


def credentials_path() -> Path:
    return config_dir() / CREDENTIALS_FILE


def load_credentials():
    path = credentials_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def save_credentials(data) -> None:
    """Write credentials with owner-only permissions (dir 0700, file 0600)."""
    directory = config_dir()
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    path = credentials_path()
    fd = os.open(str(path), os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(data, handle)
    os.chmod(path, 0o600)


def clear_credentials() -> bool:
    path = credentials_path()
    if path.exists():
        path.unlink()
        return True
    return False


def default_base_url() -> str:
    return os.environ.get("I2G_ADMIN_BASE_URL") or DEFAULT_BASE_URL


def current_base_url() -> str:
    creds = load_credentials() or {}
    return creds.get("base_url") or default_base_url()


def set_base_url(url: str) -> None:
    validate_base_url(url)
    creds = load_credentials() or {}
    creds["base_url"] = url
    save_credentials(creds)
