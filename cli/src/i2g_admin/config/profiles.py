"""Named profiles: ``config.json`` storage and profile-name resolution."""

from pathlib import Path

from ..core.errors import CliError
from . import constants, store


# --- profile resolution ----------------------------------------------------
def _config_path() -> Path:
    return store.config_dir() / constants.CONFIG_FILE


def _load_config() -> dict:
    """Return the parsed ``config.json`` (profiles + default), or ``{}`` if absent/corrupt.

    Tolerant by design for read paths: a corrupt file degrades to ``{}`` rather
    than raising, so reads (``current_base_url`` etc.) never crash. Write paths
    that must not clobber other profiles use :func:`_load_config_strict`.
    """
    data = store._read_json(_config_path())
    return data if isinstance(data, dict) else {}


def _load_config_strict() -> dict:
    """Like :func:`_load_config`, but refuse to proceed on a corrupt file.

    A missing config is fine (returns ``{}`` so a fresh one can be created), but
    a config.json that exists yet cannot be parsed raises ``CliError`` — callers
    that rewrite the file (``set_base_url``) must abort rather than rebuild from
    an empty dict and silently drop every other profile.
    """
    path = _config_path()
    data = store._read_json_raw(path)
    if data is None:
        return {}
    if data is store._CORRUPT:
        raise CliError(
            f"config.json is corrupt; refusing to overwrite it and lose other profiles. Fix or remove {path}."
        )
    return data if isinstance(data, dict) else {}


def _save_config(cfg: dict) -> None:
    store._write_secret_json(_config_path(), cfg)


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
        name = cfg.get("default_profile") or constants.DEFAULT_PROFILE
    if not constants._PROFILE_NAME_RE.match(name):
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
    return _load_config().get("default_profile") or constants.DEFAULT_PROFILE


def list_profiles() -> list[str]:
    """All known profile names: those in config.json plus the implicit default."""
    profiles = set(_profiles())
    profiles.add(constants.DEFAULT_PROFILE)
    return sorted(profiles)
