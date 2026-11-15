"""
Build ``REQUEST_RATE_LIMITS``: deep-merge the ``REQUEST_RATE_LIMITS_OVERRIDES`` JSON into the defaults, then validate
every value and the rules between them. Any problem raises ``ImproperlyConfigured`` at import, so a bad override
stops the site before it serves a request (the same contract as ``DELIVERY_RATES``).
"""

import json
from copy import deepcopy

from django.core.exceptions import ImproperlyConfigured

from .schema import OPEN_SECTIONS, OVERRIDES_ENV, SCOPE_KEY, SECTION_KEYS, SECTIONS
from .sections import (
    _check_admission,
    _check_controller,
    _check_routes,
    _check_scope,
    _check_signal_scopes,
    _check_store,
    _check_tiers,
    _check_view_scopes,
)
from .values import _fail, _keys


def validate_request_limits(config):
    """Raise ``ImproperlyConfigured`` unless ``config`` is a complete, consistent ``REQUEST_RATE_LIMITS``."""
    if not isinstance(config, dict) or set(config) != set(SECTIONS):
        _fail(("(top level)",), f"must have exactly the sections {', '.join(SECTIONS)}")
    for section in ("scopes", "routes", "exempt"):
        if not isinstance(config[section], dict):
            _fail((section,), "must be an object")
    if not config["scopes"]:
        _fail(("scopes",), "must define at least one scope")
    for name, spec in config["scopes"].items():
        if not isinstance(name, str) or not SCOPE_KEY.match(name):
            _fail(("scopes", name), "must be a lower-case key of letters, digits and hyphens")
        _check_scope(("scopes", name), spec)
    _check_view_scopes(config["scopes"])
    _check_routes(config)
    _check_tiers(config["tiers"])
    for section, required in SECTION_KEYS.items():
        _keys((section,), config[section], required)
    _check_controller(config["controller"])
    _check_signal_scopes(config["controller"], config["scopes"])
    _check_admission(config["admission"], config["abuse"])
    _check_store(config["store"], config["fallback"], config["scopes"])


def _refuse_constant(name):
    raise ValueError(f"{name} is not a number")


def _merge(target, overrides, path):
    for key, value in overrides.items():
        where = (*path, key)
        if value is None and path and path[0] in OPEN_SECTIONS:
            target.pop(key, None)  # null removes a route or an exemption
        elif key not in target:
            if not path or path[0] not in OPEN_SECTIONS:
                raise ImproperlyConfigured(f"{OVERRIDES_ENV}: {'.'.join(where)} is not a request-limit setting.")
            target[key] = deepcopy(value)
        elif isinstance(target[key], dict) and not (path and path[0] in OPEN_SECTIONS):
            if not isinstance(value, dict):
                raise ImproperlyConfigured(f"{OVERRIDES_ENV}: {'.'.join(where)} must be a JSON object.")
            _merge(target[key], value, where)
        else:
            target[key] = deepcopy(value)


def _freeze_lists(value):
    if isinstance(value, dict):
        return {key: _freeze_lists(item) for key, item in value.items()}
    if isinstance(value, list):
        return tuple(value)
    return value


def load_request_limits(defaults, raw_overrides=""):
    """Return the validated defaults with ``raw_overrides`` (the env JSON object, or blank) deep-merged in.

    An override may only replace settings that exist, except that it may add routes and exemptions (and remove one
    with ``null``); objects merge key by key (a route's method map is replaced whole), every other value is replaced
    whole.
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
    validate_request_limits(config)
    return config
