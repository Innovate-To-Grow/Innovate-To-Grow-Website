"""Environment-variable parsing helpers for production settings."""

import os

from django.core.exceptions import ImproperlyConfigured


def _get_required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ImproperlyConfigured(f"{name} must be set in production.")
    return value


def _get_int_env(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ImproperlyConfigured(f"{name} must be an integer.") from exc
    if parsed < 0:
        raise ImproperlyConfigured(f"{name} must be greater than or equal to 0.")
    return parsed


def _split_csv_env(name: str) -> list[str]:
    """Parse a comma-separated env var into a clean list (entries stripped,
    blanks dropped). Stripping matters for CSRF_TRUSTED_ORIGINS, which Django
    compares against the request Origin by exact string match — a stray space
    after a comma would otherwise reject a valid cross-origin request."""
    raw = os.environ.get(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def _get_bool_env(name: str, default: bool) -> bool:
    value = os.environ.get(name, "").strip().lower()
    if not value:
        return default
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ImproperlyConfigured(f"{name} must be a boolean value.")
