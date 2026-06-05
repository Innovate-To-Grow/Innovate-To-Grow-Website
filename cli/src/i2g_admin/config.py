import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

from .errors import CliError

# Profile names become filename suffixes (credentials-<name>.json); restrict them
# to a safe character set so a name can never escape the config dir or surprise
# the filesystem (e.g. "../../x", "a/b").
_PROFILE_NAME_RE = re.compile(r"\A[A-Za-z0-9._-]+\Z")

APP_DIR_NAME = "i2g-admin"
CREDENTIALS_FILE = "credentials.json"
CONFIG_FILE = "config.json"
DOTENV_FILE = ".env"
# Name of the environment variable (and .env key) that holds the backend base URL.
# The value itself is intentionally NOT hardcoded here: the deployment target
# lives in the environment or a .env file (see cli/.env.example), never in source.
ENV_BASE_URL = "I2G_ADMIN_BASE_URL"
# Name of the environment variable that selects the active named profile.
ENV_PROFILE = "I2G_ADMIN_PROFILE"
DEFAULT_PROFILE = "default"
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


# --- secure JSON helpers ---------------------------------------------------
def _write_secret_json(path: Path, data) -> None:
    """Write JSON with owner-only permissions (dir 0700, file 0600)."""
    directory = config_dir()
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
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


# --- profile resolution ----------------------------------------------------
def _config_path() -> Path:
    return config_dir() / CONFIG_FILE


def _load_config() -> dict:
    """Return the parsed ``config.json`` (profiles + default), or ``{}`` if absent/corrupt.

    Tolerant by design for read paths: a corrupt file degrades to ``{}`` rather
    than raising, so reads (``current_base_url`` etc.) never crash. Write paths
    that must not clobber other profiles use :func:`_load_config_strict`.
    """
    data = _read_json(_config_path())
    return data if isinstance(data, dict) else {}


def _load_config_strict() -> dict:
    """Like :func:`_load_config`, but refuse to proceed on a corrupt file.

    A missing config is fine (returns ``{}`` so a fresh one can be created), but
    a config.json that exists yet cannot be parsed raises ``CliError`` — callers
    that rewrite the file (``set_base_url``) must abort rather than rebuild from
    an empty dict and silently drop every other profile.
    """
    path = _config_path()
    data = _read_json_raw(path)
    if data is None:
        return {}
    if data is _CORRUPT:
        raise CliError(
            f"config.json is corrupt; refusing to overwrite it and lose other profiles. "
            f"Fix or remove {path}."
        )
    return data if isinstance(data, dict) else {}


def _save_config(cfg: dict) -> None:
    _write_secret_json(_config_path(), cfg)


def resolve_profile(profile: str | None = None, cfg: dict | None = None) -> str:
    """Return the profile to operate on: the explicit arg, else config.json's default, else 'default'.

    The ``--profile`` flag / ``I2G_ADMIN_PROFILE`` env var are surfaced by the CLI
    callback and passed in explicitly; this only supplies the fallback chain.

    Pass an already-loaded ``cfg`` to avoid re-reading config.json when the caller
    has it in hand (only consulted when ``profile`` is not given).
    """
    if profile:
        name = profile
    else:
        cfg = cfg if cfg is not None else _load_config()
        name = cfg.get("default_profile") or DEFAULT_PROFILE
    if not _PROFILE_NAME_RE.match(name):
        raise CliError(f"Invalid profile name {name!r}. Use only letters, digits, '.', '_' or '-'.")
    return name


def _profiles(cfg: dict | None = None) -> dict:
    """Return the ``profiles`` mapping, tolerating a corrupt/non-dict value."""
    profiles = (cfg if cfg is not None else _load_config()).get("profiles")
    return profiles if isinstance(profiles, dict) else {}


def _profile_entry(name: str, cfg: dict | None = None) -> dict:
    """Settings dict for one profile, tolerating a corrupt/non-dict entry."""
    entry = _profiles(cfg).get(name)
    return entry if isinstance(entry, dict) else {}


def default_profile() -> str:
    return _load_config().get("default_profile") or DEFAULT_PROFILE


def list_profiles() -> list[str]:
    """All known profile names: those in config.json plus the implicit default."""
    profiles = set(_profiles())
    profiles.add(DEFAULT_PROFILE)
    return sorted(profiles)


# --- credentials (per profile) ---------------------------------------------
def credentials_path(profile: str | None = None) -> Path:
    """Token file for a profile. The default profile keeps the legacy ``credentials.json``."""
    name = resolve_profile(profile)
    filename = CREDENTIALS_FILE if name == DEFAULT_PROFILE else f"credentials-{name}.json"
    return config_dir() / filename


def load_credentials(profile: str | None = None):
    return _read_json(credentials_path(profile))


def save_credentials(data, profile: str | None = None) -> None:
    _write_secret_json(credentials_path(profile), data)


def clear_credentials(profile: str | None = None) -> bool:
    path = credentials_path(profile)
    if path.exists():
        path.unlink()
        return True
    return False


# --- base URL (per profile) ------------------------------------------------
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
            "or run `i2g-admin configure set base_url <url>`."
        )
    return validate_base_url(url)


def current_base_url(profile: str | None = None) -> str:
    """The base URL for a profile: config.json override, then legacy creds, then the env default."""
    cfg = _load_config()
    name = resolve_profile(profile, cfg=cfg)
    stored = _profile_entry(name, cfg).get("base_url")
    if stored:
        return stored
    creds = load_credentials(name) or {}
    if creds.get("base_url"):
        return creds["base_url"]
    return default_base_url()


def configured_base_url(profile: str | None = None) -> str | None:
    """Return the base URL explicitly stored for a profile (config.json), or None. Never raises."""
    return _profile_entry(resolve_profile(profile)).get("base_url")


def set_base_url(url: str, profile: str | None = None) -> None:
    validate_base_url(url)
    # Strict: if config.json exists but is corrupt, abort instead of rebuilding
    # from {} and silently dropping every other profile.
    cfg = _load_config_strict()
    name = resolve_profile(profile, cfg=cfg)
    profiles = cfg.get("profiles")
    if not isinstance(profiles, dict):
        profiles = cfg["profiles"] = {}
    entry = profiles.get(name)
    if not isinstance(entry, dict):
        entry = profiles[name] = {}
    entry["base_url"] = url
    _save_config(cfg)
