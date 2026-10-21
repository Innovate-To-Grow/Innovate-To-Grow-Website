"""Per-profile bearer-token credential files."""

from pathlib import Path

from . import constants, profiles, store


def credentials_path(profile: str | None = None) -> Path:
    """Token file for a profile. The default profile keeps the legacy ``credentials.json``."""
    name = profiles.resolve_profile(profile)
    filename = (
        constants.CREDENTIALS_FILE if name == constants.DEFAULT_PROFILE else f"credentials-{name}.json"
    )
    return store.config_dir() / filename


def load_credentials(profile: str | None = None):
    return store._read_json(credentials_path(profile))


def save_credentials(data, profile: str | None = None) -> None:
    store._write_secret_json(credentials_path(profile), data)


def clear_credentials(profile: str | None = None) -> bool:
    path = credentials_path(profile)
    if path.exists():
        path.unlink()
        return True
    return False
