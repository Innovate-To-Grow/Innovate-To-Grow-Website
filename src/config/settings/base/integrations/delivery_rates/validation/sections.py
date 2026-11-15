"""Checking each section of ``DELIVERY_RATES`` and the rules between its values."""

from .schema import _STATUS_RANGE, CHANNEL_KEYS, DAY_SECONDS, HOUR_SECONDS
from .values import _CHECKS, _check_seconds, _fail


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


def _check_request_timeouts(config):
    # A send made inside a request (a sign-in code) must be able to time out within the request's budget.
    budget = config["waits"]["inline_request_budget_seconds"]
    for name, spec in config["channels"].items():
        timeout = spec.get("request_timeout_seconds")
        if timeout is not None and timeout >= budget:
            _fail(("channels", name, "request_timeout_seconds"), "must be below waits.inline_request_budget_seconds")
