"""
Build ``GMAIL_API``: apply the ``GMAIL_API_OVERRIDES`` JSON to the defaults, then validate every value and the rules
between them. Any problem raises ``ImproperlyConfigured`` at import, before the site sends anything.
"""

import json

from django.core.exceptions import ImproperlyConfigured

OVERRIDES_ENV = "GMAIL_API_OVERRIDES"
# Google's own bound on a service-account assertion: "exp" is "a maximum of 1 hour after the issued time".
MAX_ASSERTION_LIFETIME_SECONDS = 3_600
# The config's PositiveIntegerField columns these values seed.
MAX_COUNT = 2_147_483_647


def _fail(key: str, problem: str):
    raise ImproperlyConfigured(f"GMAIL_API {key} {problem}.")


def _overrides(raw: str) -> dict:
    if not raw.strip():
        return {}
    try:
        overrides = json.loads(raw)
    except ValueError:
        raise ImproperlyConfigured(f"{OVERRIDES_ENV} is not valid JSON.") from None
    if not isinstance(overrides, dict):
        raise ImproperlyConfigured(f"{OVERRIDES_ENV} must be a JSON object.")
    return overrides


def load_gmail_api(defaults: dict, raw_overrides: str) -> dict:
    """The defaults with the overrides applied; only existing keys can be overridden, and only with whole numbers."""
    values = dict(defaults)
    for key, value in _overrides(raw_overrides).items():
        if key not in defaults:
            _fail(key, "is not a setting (only existing keys can be overridden)")
        values[key] = value
    for key, value in values.items():
        if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= MAX_COUNT:
            _fail(key, f"must be a whole number from 1 to {MAX_COUNT}")
    if values["assertion_lifetime_seconds"] > MAX_ASSERTION_LIFETIME_SECONDS:
        _fail("assertion_lifetime_seconds", f"must be at most {MAX_ASSERTION_LIFETIME_SECONDS} (Google's limit)")
    if values["token_expiry_margin_seconds"] >= values["token_max_lifetime_seconds"]:
        _fail("token_expiry_margin_seconds", "must be less than token_max_lifetime_seconds")
    if values["max_message_bytes"] > values["upload_max_bytes"]:
        _fail("max_message_bytes", "must not exceed upload_max_bytes (the upload endpoint's maximum)")
    return values
