"""
Build ``REQUEST_RATE_LIMITS``: deep-merge the ``REQUEST_RATE_LIMITS_OVERRIDES`` JSON into the defaults, then validate
every value and the rules between them. Any problem raises ``ImproperlyConfigured`` at import, so a bad override
stops the site before it serves a request (the same contract as ``DELIVERY_RATES``).
"""

import json
import math
import re
from copy import deepcopy

from django.core.exceptions import ImproperlyConfigured

OVERRIDES_ENV = "REQUEST_RATE_LIMITS_OVERRIDES"
SECTIONS = ("scopes", "routes", "exempt", "tiers", "controller", "admission", "abuse", "store", "fallback")
# Mappings whose keys are data (route names), so an override may add entries to them.
OPEN_SECTIONS = frozenset({"routes", "exempt"})
TIER_ORDER = ("p0", "p1", "p2", "p3")
IDENTITY_KINDS = ("member", "session", "cli", "ip", "destination", "global", "view")
# A per-view limit (identity "view") names the route scope it sits under; it follows that scope's Smart factor.
VIEW_IDENTITY = "view"
OPTIONAL_SCOPE_KEYS = ("parent", "source_cap")
STORE_MODES = ("auto", "shared", "local")
SCOPE_KEYS = (
    "label",
    "description",
    "tier",
    "identity",
    "requests",
    "period_seconds",
    "smart_enabled",
    "smart_floor",
    "fixed",
    "enabled",
    "identity_ceiling",
    "global_cap",
)
TIER_KEYS = ("label", "decrease_factor", "recovery_step", "floor", "admission_share")
SECTION_KEYS = {
    "controller": (
        "window_seconds",
        "min_requests",
        "latency_overload_ms",
        "latency_healthy_ms",
        "error_overload_share",
        "error_healthy_share",
        "inflight_overload_share",
        "inflight_healthy_share",
        "recovery_hold_seconds",
        "max_latency_samples",
        "state_refresh_seconds",
        "min_change_seconds",
        "signal_tiers",
        "signal_excluded_scopes",
    ),
    "admission": ("concurrency_limit", "p0_reserved_slots", "retry_after_seconds"),
    "abuse": (
        "strike_window_seconds",
        "strikes_to_block",
        "block_base_seconds",
        "block_max_seconds",
        "level_memory_seconds",
        "proof_promotions",
        "proof_memory_seconds",
    ),
    "store": (
        "mode",
        "shared_backends",
        "heartbeat_seconds",
        "process_expiry_seconds",
        "process_prune_seconds",
        "refusal_history_minutes",
    ),
    "fallback": (
        "cli_prefix",
        "admin_prefix",
        "cli",
        "admin",
        "public_read",
        "public_write",
        "member_read",
        "member_write",
        "not_found",
        "unproven",
    ),
}
FALLBACK_SCOPES = (
    "cli",
    "admin",
    "public_read",
    "public_write",
    "member_read",
    "member_write",
    "not_found",
    "unproven",
)
# The policy columns: counts are PositiveIntegerField, periods at most a day, shares Decimal(4, 3).
MAX_COUNT = 2_147_483_647
MAX_PERIOD = 86_400
MAX_SECONDS = 366 * 86_400
# The admin reads the recent 429s as one key per scope, kind and minute in one call: two hours at most.
MAX_HISTORY_MINUTES = 120
SCOPE_KEY = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
METHOD = re.compile(r"^(\*|[A-Z]+)$")


def _fail(path, problem):
    raise ImproperlyConfigured(f"REQUEST_RATE_LIMITS {'.'.join(str(part) for part in path)} {problem}.")


def _number(value) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def _count(path, value, low=1, high=MAX_COUNT):
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        _fail(path, f"must be a whole number between {low} and {high}")


def _fraction(path, value, *, below_one=False):
    if not _number(value) or not 0 < value <= 1 or (below_one and value >= 1):
        _fail(path, "must be a share greater than 0 and " + ("below 1" if below_one else "at most 1"))


def _seconds(path, value, low=0.0):
    if not _number(value) or not low < value <= MAX_SECONDS:
        _fail(path, f"must be a number of seconds above {low:g} and at most {MAX_SECONDS}")


def _bool(path, value):
    if not isinstance(value, bool):
        _fail(path, "must be true or false")


def _text(path, value, *, blank=False):
    if not isinstance(value, str) or (not blank and not value.strip()):
        _fail(path, "must be " + ("text" if blank else "non-empty text"))


def _keys(path, values, required):
    if not isinstance(values, dict):
        _fail(path, "must be an object")
    if set(values) != set(required):
        _fail(path, f"must have exactly the keys {', '.join(required)}")


def _below(path, low, high, problem):
    if low >= high:
        _fail(path, problem)


def _check_scope(path, spec):
    if not isinstance(spec, dict):
        _fail(path, "must be an object")
    _keys(path, {key: value for key, value in spec.items() if key not in OPTIONAL_SCOPE_KEYS}, SCOPE_KEYS)
    _text((*path, "label"), spec["label"])
    _text((*path, "description"), spec["description"], blank=True)
    if spec["tier"] not in TIER_ORDER:
        _fail((*path, "tier"), f"must be one of {', '.join(TIER_ORDER)}")
    if spec["identity"] not in IDENTITY_KINDS:
        _fail((*path, "identity"), f"must be one of {', '.join(IDENTITY_KINDS)}")
    _count((*path, "requests"), spec["requests"])
    _count((*path, "period_seconds"), spec["period_seconds"], high=MAX_PERIOD)
    for key in ("smart_enabled", "fixed", "enabled"):
        _bool((*path, key), spec[key])
    if spec["smart_floor"] is not None:
        _fraction((*path, "smart_floor"), spec["smart_floor"])
    for key in ("identity_ceiling", "global_cap", "source_cap"):
        if spec.get(key) is not None:
            _count((*path, key), spec[key])
    if spec["identity"] == "global" and spec["global_cap"] is None:
        _fail((*path, "global_cap"), 'must be set for identity "global" (it is the only limit)')
    if spec["identity_ceiling"] is not None and spec["requests"] > spec["identity_ceiling"]:
        _fail((*path, "requests"), "must not be above identity_ceiling")


def is_view_scope(spec) -> bool:
    return spec.get("identity") == VIEW_IDENTITY


def _check_view_scopes(scopes):
    """A per-view limit names a route scope as its parent, and only a per-view limit has one."""
    for name, spec in scopes.items():
        path = ("scopes", name)
        if not is_view_scope(spec):
            if "parent" in spec:
                _fail((*path, "parent"), 'is only for a per-view limit (identity "view")')
            continue
        parent = spec.get("parent")
        if not isinstance(parent, str) or parent not in scopes or is_view_scope(scopes[parent]):
            _fail((*path, "parent"), "must name a route scope (not a per-view limit) in REQUEST_RATE_LIMITS.scopes")
        for key in ("global_cap", "source_cap"):
            if spec.get(key) is not None:
                _fail((*path, key), "must be null: a per-view limit keeps its own key")


def _check_scope_value(path, value, scopes):
    if isinstance(value, dict):
        if not value:
            _fail(path, "must name at least one method")
        for method, scope in value.items():
            if not isinstance(method, str) or not METHOD.match(method):
                _fail((*path, method), 'must be an upper-case HTTP method or "*"')
            _check_scope_value((*path, method), scope, scopes)
    elif value not in scopes:
        _fail(path, "must name a scope in REQUEST_RATE_LIMITS.scopes")
    elif is_view_scope(scopes[value]):
        _fail(path, "names a per-view limit; a route needs a route scope")


def _check_routes(config):
    scopes = config["scopes"]
    for name, value in config["routes"].items():
        _text(("routes", name), name)
        _check_scope_value(("routes", name), value, scopes)
    for name, reason in config["exempt"].items():
        _text(("exempt", name), reason)
        if name in config["routes"]:
            _fail(("exempt", name), "is also in routes; a route is either limited or exempt")


def _check_tiers(tiers):
    if not isinstance(tiers, dict) or tuple(tiers) != TIER_ORDER:
        _fail(("tiers",), f"must list exactly the tiers {', '.join(TIER_ORDER)} in that order")
    _keys(("tiers", "p0"), tiers["p0"], ("label",))
    _text(("tiers", "p0", "label"), tiers["p0"]["label"])
    shares = []
    for tier in TIER_ORDER[1:]:
        spec = tiers[tier]
        _keys(("tiers", tier), spec, TIER_KEYS)
        _text(("tiers", tier, "label"), spec["label"])
        _fraction(("tiers", tier, "decrease_factor"), spec["decrease_factor"], below_one=True)
        for key in ("recovery_step", "floor", "admission_share"):
            _fraction(("tiers", tier, key), spec[key])
        shares.append(spec["admission_share"])
    if shares != sorted(shares, reverse=True):
        _fail(("tiers",), "admission_share must not grow from p1 to p3 (a lower tier never gets more slots)")


def _check_signal_scopes(values, scopes):
    tiers = values["signal_tiers"]
    if not isinstance(tiers, tuple) or not tiers or any(tier not in TIER_ORDER for tier in tiers):
        _fail(("controller", "signal_tiers"), f"must be a non-empty list of tiers from {', '.join(TIER_ORDER)}")
    excluded = values["signal_excluded_scopes"]
    if not isinstance(excluded, tuple) or any(name not in scopes for name in excluded):
        _fail(("controller", "signal_excluded_scopes"), "must be a list of scopes in REQUEST_RATE_LIMITS.scopes")


def _check_controller(values):
    _seconds(("controller", "min_change_seconds"), values["min_change_seconds"], low=-1)
    for key in ("window_seconds", "state_refresh_seconds"):
        _seconds(("controller", key), values[key])
    _seconds(("controller", "recovery_hold_seconds"), values["recovery_hold_seconds"], low=-1)
    _count(("controller", "min_requests"), values["min_requests"])
    _count(("controller", "max_latency_samples"), values["max_latency_samples"])
    for key in ("latency_overload_ms", "latency_healthy_ms"):
        if not _number(values[key]) or values[key] <= 0:
            _fail(("controller", key), "must be a number of milliseconds above 0")
    for key in ("error_overload_share", "error_healthy_share", "inflight_overload_share", "inflight_healthy_share"):
        _fraction(("controller", key), values[key])
    for signal, unit in (("latency", "ms"), ("error", "share"), ("inflight", "share")):
        _below(
            ("controller", f"{signal}_healthy_{unit}"),
            values[f"{signal}_healthy_{unit}"],
            values[f"{signal}_overload_{unit}"],
            f"must be below {signal}_overload_{unit}",
        )


def _check_admission(admission, abuse):
    _count(("admission", "concurrency_limit"), admission["concurrency_limit"])
    _count(("admission", "p0_reserved_slots"), admission["p0_reserved_slots"], low=1)
    _below(
        ("admission", "p0_reserved_slots"),
        admission["p0_reserved_slots"],
        admission["concurrency_limit"],
        "must be below concurrency_limit",
    )
    _seconds(("admission", "retry_after_seconds"), admission["retry_after_seconds"])
    _count(("abuse", "strikes_to_block"), abuse["strikes_to_block"])
    for key in ("strike_window_seconds", "block_base_seconds", "block_max_seconds", "level_memory_seconds"):
        _seconds(("abuse", key), abuse[key])
    _count(("abuse", "proof_promotions"), abuse["proof_promotions"])
    _seconds(("abuse", "proof_memory_seconds"), abuse["proof_memory_seconds"])
    if abuse["block_base_seconds"] > abuse["block_max_seconds"]:
        _fail(("abuse", "block_base_seconds"), "must not be above block_max_seconds")


def _check_store(store, fallback, scopes):
    if store["mode"] not in STORE_MODES:
        _fail(("store", "mode"), f"must be one of {', '.join(STORE_MODES)}")
    backends = store["shared_backends"]
    if not isinstance(backends, tuple) or not backends or not all(isinstance(item, str) and item for item in backends):
        _fail(("store", "shared_backends"), "must be a non-empty list of cache backend paths")
    for key in ("heartbeat_seconds", "process_expiry_seconds", "process_prune_seconds"):
        _seconds(("store", key), store[key])
    _below(
        ("store", "heartbeat_seconds"),
        store["heartbeat_seconds"],
        store["process_expiry_seconds"],
        "must be below process_expiry_seconds (a live process must refresh its row before it expires)",
    )
    if store["process_prune_seconds"] < store["process_expiry_seconds"]:
        _fail(("store", "process_prune_seconds"), "must not be below process_expiry_seconds")
    _count(("store", "refusal_history_minutes"), store["refusal_history_minutes"], high=MAX_HISTORY_MINUTES)
    for key in ("cli_prefix", "admin_prefix"):
        value = fallback[key]
        if not isinstance(value, str) or len(value) < 3 or not value.startswith("/") or not value.endswith("/"):
            _fail(("fallback", key), 'must be a path such as "/admin/"')
    for key in FALLBACK_SCOPES:
        if fallback[key] not in scopes or is_view_scope(scopes[fallback[key]]):
            _fail(("fallback", key), "must name a route scope in REQUEST_RATE_LIMITS.scopes")


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
