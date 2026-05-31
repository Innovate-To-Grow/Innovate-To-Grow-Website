import json
import os
from pathlib import Path
from urllib.parse import urlparse

from .errors import CliError

APP_DIR_NAME = "i2g-admin"
CREDENTIALS_FILE = "credentials.json"
DOTENV_FILE = ".env"
# Name of the environment variable (and .env key) that holds the backend base URL.
# The value itself is intentionally NOT hardcoded here: the deployment target
# lives in the environment or a .env file (see cli/.env.example), never in source.
ENV_BASE_URL = "I2G_ADMIN_BASE_URL"
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


def _package_root() -> Path:
    """The cli/ directory: config.py -> i2g_admin -> src -> cli."""
    return Path(__file__).resolve().parent.parent.parent


def _dotenv_paths() -> list[Path]:
    """.env locations, highest precedence first: current dir, then the cli/ root."""
    return [Path.cwd() / DOTENV_FILE, _package_root() / DOTENV_FILE]


def _parse_dotenv(text: str) -> dict[str, str]:
    """Parse ``KEY=value`` lines; ignore blanks/``#`` comments; strip optional quotes."""
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key:
            values[key] = value.strip().strip('"').strip("'")
    return values


def load_dotenv() -> None:
    """Populate ``os.environ`` from the nearest .env file, never overriding real env vars.

    Minimal, dependency-free loader. A value already present in the process
    environment always wins, so an explicit shell export beats the file, and the
    first .env found beats later ones.
    """
    for path in _dotenv_paths():
        if not path.is_file():
            continue
        for key, value in _parse_dotenv(path.read_text()).items():
            os.environ.setdefault(key, value)


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
    """Resolve the backend base URL from the environment / .env file.

    ``I2G_ADMIN_BASE_URL`` (exported, or supplied via a .env file) is the single
    source of truth. There is deliberately no baked-in fallback host, so a
    missing value is a clear configuration error rather than a silent default.
    """
    load_dotenv()
    url = os.environ.get(ENV_BASE_URL)
    if not url:
        raise CliError(
            f"No backend base URL configured. Set {ENV_BASE_URL} in your environment "
            "or a .env file (copy cli/.env.example to cli/.env), "
            "or run `i2g-admin configure --base-url <url>`."
        )
    return validate_base_url(url)


def current_base_url() -> str:
    creds = load_credentials() or {}
    return creds.get("base_url") or default_base_url()


def set_base_url(url: str) -> None:
    validate_base_url(url)
    creds = load_credentials() or {}
    creds["base_url"] = url
    save_credentials(creds)
