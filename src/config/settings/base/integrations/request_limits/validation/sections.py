"""Checking each section of ``REQUEST_RATE_LIMITS`` and the rules between them."""

from .schema import (
    FALLBACK_SCOPES,
    IDENTITY_KINDS,
    MAX_HISTORY_MINUTES,
    MAX_PERIOD,
    METHOD,
    OPTIONAL_SCOPE_KEYS,
    SCOPE_KEYS,
    STORE_MODES,
    TIER_KEYS,
    TIER_ORDER,
    VIEW_IDENTITY,
)
from .values import _below, _bool, _count, _fail, _fraction, _keys, _number, _seconds, _text


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
