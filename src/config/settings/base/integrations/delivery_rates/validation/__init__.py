"""Build ``DELIVERY_RATES``: deep-merge the ``DELIVERY_RATES_OVERRIDES`` JSON into the defaults, then validate every
value and the rules between them (``loading``). ``schema`` holds what the setting may contain, ``values`` and
``sections`` the checks."""

from .loading import (
    load_delivery_rates,
    validate_delivery_rates,
)
from .schema import (
    CHANNEL_KEYS,
    DAY_SECONDS,
    HOST_PROFILE_KEYS,
    HOUR_SECONDS,
    MAX_COUNT,
    MAX_RATE,
    MAX_RESERVE,
    MAX_SECONDS,
    MIN_RATE,
    MIN_SHARE,
    OPEN_MAPPINGS,
    OVERRIDES_ENV,
    SECTION_KEYS,
    SECTIONS,
)

__all__ = [
    "OVERRIDES_ENV",
    "SECTIONS",
    "OPEN_MAPPINGS",
    "MIN_RATE",
    "MAX_RATE",
    "MAX_COUNT",
    "MIN_SHARE",
    "MAX_RESERVE",
    "MAX_SECONDS",
    "DAY_SECONDS",
    "HOUR_SECONDS",
    "CHANNEL_KEYS",
    "HOST_PROFILE_KEYS",
    "SECTION_KEYS",
    "validate_delivery_rates",
    "load_delivery_rates",
]
