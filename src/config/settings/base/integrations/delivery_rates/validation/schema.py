"""What ``DELIVERY_RATES`` may hold: its sections and keys, and the bounds of the policy columns it seeds."""

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
