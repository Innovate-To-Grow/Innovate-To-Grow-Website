"""Backend base-URL validation and per-profile resolution."""

import os
from urllib.parse import urlparse

from ..core.errors import CliError
from . import constants, credentials, dotenv, profiles


def validate_base_url(url: str) -> str:
    """Return the URL if it is https (any host) or http to a loopback host; else raise."""
    parsed = urlparse(url or "")
    if parsed.scheme == "https" and parsed.netloc:
        return url
    if parsed.scheme == "http" and parsed.hostname in constants.LOOPBACK_HOSTS:
        return url
    raise CliError(f"base_url must be https, or http on a loopback host (got {url!r}).")


def default_base_url() -> str:
    """Resolve the backend base URL from the environment / .env file.

    ``I2G_ADMIN_BASE_URL`` (exported, or supplied via a .env file) is the single
    source of truth. There is deliberately no baked-in fallback host, so a
    missing value is a clear configuration error rather than a silent default.
    """
    dotenv.load_dotenv()
    url = os.environ.get(constants.ENV_BASE_URL)
    if not url:
        raise CliError(
            f"No backend base URL configured. Set {constants.ENV_BASE_URL} in your environment "
            "or a .env file (copy cli/.env.example to cli/.env), "
            "or run `i2g-admin configure set base_url <url>`."
        )
    return validate_base_url(url)


def current_base_url(profile: str | None = None) -> str:
    """The base URL for a profile: config.json override, then legacy creds, then the env default."""
    cfg = profiles._load_config()
    name = profiles.resolve_profile(profile, cfg=cfg)
    stored = profiles._profile_entry(name, cfg).get("base_url")
    if stored:
        return stored
    creds = credentials.load_credentials(name) or {}
    if creds.get("base_url"):
        return creds["base_url"]
    return default_base_url()


def configured_base_url(profile: str | None = None) -> str | None:
    """Return the base URL explicitly stored for a profile (config.json), or None. Never raises."""
    return profiles._profile_entry(profiles.resolve_profile(profile)).get("base_url")


def set_base_url(url: str, profile: str | None = None) -> None:
    validate_base_url(url)
    # Strict: if config.json exists but is corrupt, abort instead of rebuilding
    # from {} and silently dropping every other profile.
    cfg = profiles._load_config_strict()
    name = profiles.resolve_profile(profile, cfg=cfg)
    profile_map = cfg.get("profiles")
    if not isinstance(profile_map, dict):
        profile_map = cfg["profiles"] = {}
    entry = profile_map.get(name)
    if not isinstance(entry, dict):
        entry = profile_map[name] = {}
    entry["base_url"] = url
    profiles._save_config(cfg)
