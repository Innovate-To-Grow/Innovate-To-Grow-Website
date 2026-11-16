"""
Build ``DELIVERY_RATES``: deep-merge the ``DELIVERY_RATES_OVERRIDES`` JSON into the defaults, then validate every
value and the rules between them. Any problem raises ``ImproperlyConfigured`` at import, so a bad override stops
the site (and every management command) before it sends anything.
"""

import json
from copy import deepcopy

from django.core.exceptions import ImproperlyConfigured

from .schema import OPEN_MAPPINGS, OVERRIDES_ENV, SECTION_KEYS, SECTIONS
from .sections import (
    _check_channel,
    _check_controller,
    _check_mapping,
    _check_patterns,
    _check_request_timeouts,
    _check_runtime,
    _check_section,
)
from .values import _fail


def validate_delivery_rates(config):
    """Raise ``ImproperlyConfigured`` unless ``config`` is a complete, consistent ``DELIVERY_RATES``."""
    if not isinstance(config, dict) or set(config) != set(SECTIONS):
        _fail(("(top level)",), f"must have exactly the sections {', '.join(SECTIONS)}")
    for section in ("channels", "signals"):
        _check_mapping((section,), config[section])
    for name, spec in config["channels"].items():
        _check_channel(("channels", name), spec)
    for adapter, patterns in config["signals"].items():
        _check_mapping(("signals", adapter), patterns)
        for name, value in patterns.items():
            _check_patterns(("signals", adapter, name), value)
    for section, required in SECTION_KEYS.items():
        _check_section((section,), config[section], required)
    _check_controller(config["controller"])
    _check_runtime(config)
    _check_request_timeouts(config)


def _refuse_constant(name):
    raise ValueError(f"{name} is not a number")


def _merge(target, overrides, path):
    for key, value in overrides.items():
        where = (*path, key)
        if key not in target:
            if not any(path[: len(open_path)] == open_path for open_path in OPEN_MAPPINGS):
                raise ImproperlyConfigured(f"{OVERRIDES_ENV}: {'.'.join(where)} is not a delivery-rate setting.")
            target[key] = deepcopy(value)
        elif isinstance(target[key], dict):
            if not isinstance(value, dict):
                raise ImproperlyConfigured(f"{OVERRIDES_ENV}: {'.'.join(where)} must be a JSON object.")
            _merge(target[key], value, where)
        else:
            target[key] = deepcopy(value)


def _freeze_lists(value):
    """JSON overrides bring lists; keep every pattern list a tuple, like the defaults."""
    if isinstance(value, dict):
        return {key: _freeze_lists(item) for key, item in value.items()}
    if isinstance(value, list):
        return tuple(value)
    return value


def load_delivery_rates(defaults, raw_overrides=""):
    """Return the validated defaults with ``raw_overrides`` (the env JSON object, or blank) deep-merged in.

    An override may only replace settings that exist (a typo is an error, not a silently ignored key); objects
    merge key by key, and every other value, lists included, is replaced whole.
    """
    config = deepcopy(defaults)
    if raw_overrides and raw_overrides.strip():
        try:
            overrides = json.loads(raw_overrides, parse_constant=_refuse_constant)
        except ValueError:
            raise ImproperlyConfigured(f"{OVERRIDES_ENV} must be valid JSON.") from None
        if not isinstance(overrides, dict):
            raise ImproperlyConfigured(f"{OVERRIDES_ENV} must be a JSON object.")
        _merge(config, overrides, ())
    config = _freeze_lists(config)
    validate_delivery_rates(config)
    return config
