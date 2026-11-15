"""Checking one value (a rate, share, count, number of seconds, domain or host profile), and which check each key
gets."""

import math

from django.core.exceptions import ImproperlyConfigured, ValidationError

from .schema import (
    _DOMAIN_VALIDATOR,
    HOST_PROFILE_KEYS,
    MAX_COUNT,
    MAX_RATE,
    MAX_RESERVE,
    MAX_SECONDS,
    MIN_RATE,
    MIN_SHARE,
)


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
    "max_recipients_per_message": _check_count,
    "daily_limit": _check_optional_count,
    "hourly_external_limit": _check_optional_count,
    "hourly_internal_limit": _check_optional_count,
    "daily_message_limit": _check_optional_count,
    "daily_external_limit": _check_optional_count,
    "internal_domain": _check_domain,
    "host_profiles": _check_host_profiles,
}
