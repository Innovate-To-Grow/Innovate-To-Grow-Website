"""Build ``REQUEST_RATE_LIMITS``: deep-merge the ``REQUEST_RATE_LIMITS_OVERRIDES`` JSON into the defaults, then validate
every value and the rules between them (``loading``). Any problem raises ``ImproperlyConfigured`` at import, so a
bad override stops the site before it serves a request (the same contract as ``DELIVERY_RATES``). ``schema`` holds
what the setting may contain, ``values`` and ``sections`` the checks."""

from .loading import (
    load_request_limits,
    validate_request_limits,
)
from .schema import (
    FALLBACK_SCOPES,
    IDENTITY_KINDS,
    MAX_COUNT,
    MAX_HISTORY_MINUTES,
    MAX_PERIOD,
    MAX_SECONDS,
    METHOD,
    OPEN_SECTIONS,
    OPTIONAL_SCOPE_KEYS,
    OVERRIDES_ENV,
    SCOPE_KEY,
    SCOPE_KEYS,
    SECTION_KEYS,
    SECTIONS,
    STORE_MODES,
    TIER_KEYS,
    TIER_ORDER,
    VIEW_IDENTITY,
)
from .sections import (
    is_view_scope,
)

__all__ = [
    "OVERRIDES_ENV",
    "SECTIONS",
    "OPEN_SECTIONS",
    "TIER_ORDER",
    "IDENTITY_KINDS",
    "VIEW_IDENTITY",
    "OPTIONAL_SCOPE_KEYS",
    "STORE_MODES",
    "SCOPE_KEYS",
    "TIER_KEYS",
    "SECTION_KEYS",
    "FALLBACK_SCOPES",
    "MAX_COUNT",
    "MAX_PERIOD",
    "MAX_SECONDS",
    "MAX_HISTORY_MINUTES",
    "SCOPE_KEY",
    "METHOD",
    "is_view_scope",
    "validate_request_limits",
    "load_request_limits",
]
