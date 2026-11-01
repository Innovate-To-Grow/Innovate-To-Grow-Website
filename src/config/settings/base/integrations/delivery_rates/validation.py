"""
Build ``DELIVERY_RATES``: deep-merge the ``DELIVERY_RATES_OVERRIDES`` JSON into the defaults, then validate every
value and the rules between them. Any problem raises ``ImproperlyConfigured`` at import, so a bad override stops
the site (and every management command) before it sends anything.
"""

import json
import math
from copy import deepcopy

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.validators import DomainNameValidator

OVERRIDES_ENV = "DELIVERY_RATES_OVERRIDES"
SECTIONS = ("channels", "controller", "waits", "lanes", "usage", "discovery", "jobs", "signals")
# Mappings whose keys are data, not setting names: an override may add entries to them, or to the objects inside
# them (another SMTP host, or another limit for a known host).
OPEN_MAPPINGS = frozenset({("channels", "smtp_send", "host_profiles")})

# The DeliveryRatePolicy columns these values seed: rates are Decimal(10, 3), counts PositiveIntegerField, and the
# budget headroom and transactional reserve Decimal(4, 3) shares.
MIN_RATE = 0.001
MAX_RATE = 9_999_999.999
MAX_COUNT = 2_147_483_647
MIN_SHARE = 0.001
MAX_RESERVE = 0.999
# No wait, interval or retention here is meaningfully longer than a year; the bound keeps datetime arithmetic finite.
MAX_SECONDS = 366 * 86_400
# The daily limits are rolling 24 h windows and the Graph per-hour limits rolling 1 h windows (definitions, not
# tunables): the usage buckets must tile an hour and be kept for at least a day.
DAY_SECONDS = 86_400
HOUR_SECONDS = 3_600
_DOMAIN_VALIDATOR = DomainNameValidator(accept_idna=False)
# HTTP statuses and SMTP reply codes are three-digit numbers.
_STATUS_RANGE = range(100, 600)
CHANNEL_KEYS = (
    "smart_enabled",
    "manual_rate",
    "provider_limit",
    "fallback_rate",
    "headroom",
    "burst",
    "recovery_interval_seconds",
    "backoff_initial_seconds",
    "backoff_max_seconds",
)
HOST_PROFILE_KEYS = frozenset({"daily_limit", "daily_message_limit"})
# Settings the limiter and the rules below read from each runtime section.
SECTION_KEYS = {
    "controller": (
        "start_factor",
        "start_factor_without_limit",
        "decrease_factor",
        "recovery_step",
        "floor",
        "backoff_jitter",
        "retry_after_max_seconds",
        "persistent_throttle_count",
        "breaker_probe_seconds",
        "breaker_probe_max_seconds",
    ),
    "waits": ("inline_seconds", "read_seconds", "worker_seconds", "dedicated_seconds", "inline_request_budget_seconds"),
    "lanes": ("bulk_share", "transactional_reserve"),
    "usage": ("bucket_seconds", "retention_seconds", "idle_state_seconds"),
    "discovery": ("timeout_seconds", "min_refresh_after_throttle_seconds"),
    "jobs": (
        "retry_base_seconds",
        "retry_max_seconds",
        "default_max_attempts",
        "stale_claim_seconds",
        "defer_jitter_seconds",
        "gate_cache_seconds",
        "runner_refresh_recipients",
    ),
}


def _fail(path, problem):
    raise ImproperlyConfigured(f"DELIVERY_RATES {'.'.join(path)} {problem}.")


def _is_number(value) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def _check_bool(path, value):
    if not isinstance(value, bool):
        _fail(path, "must be true or false")


def _check_rate(path, value):
    if not _is_number(value) or not MIN_RATE <= value <= MAX_RATE:
        _fail(path, f"must be a rate between {MIN_RATE} and {MAX_RATE}")


def _check_optional_rate(path, value):
    if value is not None:
        _check_rate(path, value)


def _check_fraction(path, value):
    if not _is_number(value) or not 0 < value <= 1:
        _fail(path, "must be a fraction greater than 0 and at most 1")


def _check_budget_share(path, value):
    if not _is_number(value) or not MIN_SHARE <= value <= 1:
        _fail(path, f"must be a share between {MIN_SHARE} and 1")


def _check_reserve(path, value):
    # 0 leaves campaigns the whole budget; 1 would leave them nothing, so it is refused.
    if value is not None and (not _is_number(value) or not 0 <= value <= MAX_RESERVE):
        _fail(path, f"must be a share between 0 and {MAX_RESERVE}")


def _check_jitter(path, value):
    if not _is_number(value) or not 0 <= value < 1:
        _fail(path, "must be a share of at least 0 and below 1")


def _check_count(path, value):
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= MAX_COUNT:
        _fail(path, f"must be a whole number between 1 and {MAX_COUNT}")


def _check_optional_count(path, value):
    if value is not None:
        _check_count(path, value)


def _check_seconds(path, value):
    if not _is_number(value) or not 0 < value <= MAX_SECONDS:
        _fail(path, f"must be a number of seconds above 0 and at most {MAX_SECONDS}")


def _check_domain(path, value):
    if not isinstance(value, str) or value != value.strip().lower():
        _fail(path, "must be blank or a lower-case domain name such as example.edu")
    if value:
        try:
            _DOMAIN_VALIDATOR(value)
        except ValidationError:
            _fail(path, "must be blank or a lower-case domain name such as example.edu")


def _check_host_profiles(path, value):
    if not isinstance(value, dict):
        _fail(path, "must be an object of host names")
    for host, limits in value.items():
        where = (*path, str(host))
        if not isinstance(host, str) or not host.strip() or host != host.strip().lower():
            _fail(where, "must be a lower-case host name")
        if not isinstance(limits, dict) or not limits or set(limits) - HOST_PROFILE_KEYS:
            _fail(where, f"must set one or more of: {', '.join(sorted(HOST_PROFILE_KEYS))}")
        for key, limit in limits.items():
            _check_count((*where, key), limit)


_CHECKS = {
    "smart_enabled": _check_bool,
    "limits_confirmed": _check_bool,
    "manual_rate": _check_rate,
    "parts_fallback_rate": _check_rate,
    "provider_limit": _check_optional_rate,
    "parts_limit": _check_optional_rate,
    "fallback_rate": _check_optional_rate,
    "headroom": _check_fraction,
    "budget_headroom": _check_budget_share,
    "start_factor": _check_fraction,
    "start_factor_without_limit": _check_fraction,
    "decrease_factor": _check_fraction,
    "recovery_step": _check_fraction,
    "floor": _check_fraction,
    "bulk_share": _check_fraction,
    "transactional_reserve": _check_reserve,
    "backoff_jitter": _check_jitter,
    "burst": _check_count,
    "persistent_throttle_count": _check_count,
    "default_max_attempts": _check_count,
    "runner_refresh_recipients": _check_count,
    "unconfirmed_bulk_daily_limit": _check_count,
    "daily_limit": _check_optional_count,
    "hourly_external_limit": _check_optional_count,
    "hourly_internal_limit": _check_optional_count,
    "daily_message_limit": _check_optional_count,
    "daily_external_limit": _check_optional_count,
    "internal_domain": _check_domain,
    "host_profiles": _check_host_profiles,
}


def _check_value(path, value):
    key = path[-1]
    check = _check_seconds if key.endswith("_seconds") else _CHECKS.get(key)
    if check is None:
        _fail(path, "is not a known delivery-rate setting")
    check(path, value)


def _check_patterns(path, value):
    if not isinstance(value, list | tuple) or not value:
        _fail(path, "must be a non-empty list")
    for item in value:
        if path[-1].endswith("_statuses"):
            if not isinstance(item, int) or isinstance(item, bool) or item not in _STATUS_RANGE:
                _fail(path, "must list three-digit status codes")
        elif not isinstance(item, str) or not item.strip():
            _fail(path, "must list non-empty strings")


def _check_mapping(path, value):
    if not isinstance(value, dict):
        _fail(path, "must be an object")


def _limit_below(spec, path, smaller, larger, problem):
    low, high = spec.get(smaller), spec.get(larger)
    if low is not None and high is not None and low > high:
        _fail((*path, smaller), problem)


def _check_section(path, values, required):
    _check_mapping(path, values)
    missing = [key for key in required if key not in values]
    if missing:
        _fail(path, f"is missing {', '.join(missing)}")
    for key, value in values.items():
        _check_value((*path, key), value)


def _check_channel(path, spec):
    _check_section(path, spec, CHANNEL_KEYS)
    if spec["provider_limit"] is None and spec["fallback_rate"] is None:
        _fail(path, "needs a provider_limit or a fallback_rate (Smart rate needs a bound)")
    _limit_below(spec, path, "manual_rate", "provider_limit", "must not be above provider_limit")
    _limit_below(spec, path, "backoff_initial_seconds", "backoff_max_seconds", "must not be above the maximum")
    for smaller in ("hourly_external_limit", "hourly_internal_limit", "daily_external_limit"):
        _limit_below(spec, path, smaller, "daily_limit", "must not be above daily_limit")
    _limit_below(spec, path, "unconfirmed_bulk_daily_limit", "daily_limit", "must not be above daily_limit")


def _check_controller(controller):
    if not controller["floor"] <= controller["start_factor_without_limit"] <= controller["start_factor"]:
        _fail(("controller", "floor"), "must not be above start_factor_without_limit, nor that above start_factor")
    if controller["decrease_factor"] >= 1:
        _fail(("controller", "decrease_factor"), "must be below 1 (Smart rate must slow down on a throttle)")
    if controller["breaker_probe_seconds"] > controller["breaker_probe_max_seconds"]:
        _fail(("controller", "breaker_probe_seconds"), "must not be above breaker_probe_max_seconds")


def _check_runtime(config):
    waits, jobs, usage = config["waits"], config["jobs"], config["usage"]
    if waits["worker_seconds"] >= jobs["stale_claim_seconds"]:
        _fail(("waits", "worker_seconds"), "must be below jobs.stale_claim_seconds (the stale-claim recovery)")
    for key in ("inline_seconds", "read_seconds"):
        if waits[key] >= waits["inline_request_budget_seconds"]:
            _fail(("waits", key), "must be below waits.inline_request_budget_seconds")
    if jobs["retry_base_seconds"] > jobs["retry_max_seconds"]:
        _fail(("jobs", "retry_base_seconds"), "must not be above retry_max_seconds")
    bucket = usage["bucket_seconds"]
    if not isinstance(bucket, int) or HOUR_SECONDS % bucket:
        _fail(("usage", "bucket_seconds"), "must be a whole number of seconds that divides one hour")
    if usage["retention_seconds"] < DAY_SECONDS + bucket:
        _fail(("usage", "retention_seconds"), "must cover 24 hours plus one bucket")
    if usage["idle_state_seconds"] < usage["retention_seconds"]:
        _fail(("usage", "idle_state_seconds"), "must not be below retention_seconds")
    if config["lanes"]["transactional_reserve"] is None:
        _fail(("lanes", "transactional_reserve"), "must be set")


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
