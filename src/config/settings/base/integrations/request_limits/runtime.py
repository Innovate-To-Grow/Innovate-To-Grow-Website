"""
How Smart limiting reacts, how slots are shared between priority tiers, abuse escalation and the counter store.

These are app defaults (nothing documents them); each comment says what the value does.
"""

import os

from django.core.exceptions import ImproperlyConfigured


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        raise ImproperlyConfigured(f"{name} must be a whole number.") from None


TIER_ORDER = ("p0", "p1", "p2", "p3")

TIERS = {
    # Critical: never tightened for load and may use every slot; only its abuse limits apply.
    "p0": {"label": "P0 critical"},
    # Interactive: shed last, by a little each step, and restored first.
    "p1": {
        "label": "P1 interactive",
        # Each overloaded evaluation multiplies the tier's Smart factor by this...
        "decrease_factor": 0.85,
        # ...each healthy one adds this back (up to 1)...
        "recovery_step": 0.15,
        # ...and the factor never falls below this share of the baseline (a scope's smart_floor seed).
        "floor": 0.5,
        # Requests of this tier may occupy at most this share of a process's concurrency slots.
        "admission_share": 0.9,
    },
    # Background: polling, telemetry, prefetch.
    "p2": {
        "label": "P2 background",
        "decrease_factor": 0.7,
        "recovery_step": 0.10,
        "floor": 0.25,
        "admission_share": 0.7,
    },
    # Heavy / bulk / AI / scanners: shed first and hardest, restored last.
    "p3": {"label": "P3 heavy", "decrease_factor": 0.5, "recovery_step": 0.10, "floor": 0.1, "admission_share": 0.5},
}

CONTROLLER = {
    # Signals are measured per process in windows of this length; each closed window is evaluated once.
    "window_seconds": 15,
    # A window needs this many requests before its latency and error share count (site-wide and per scope).
    "min_requests": 20,
    # p95 response time (ms) at or above which the site is overloaded, and below which it is healthy.
    "latency_overload_ms": 1_500,
    "latency_healthy_ms": 800,
    # Share of 5xx responses at or above which the site is overloaded, and below which it is healthy.
    "error_overload_share": 0.05,
    "error_healthy_share": 0.01,
    # Mean share of the process's concurrency slots in use at or above which it is overloaded / below which healthy.
    "inflight_overload_share": 0.75,
    "inflight_healthy_share": 0.4,
    # A scope cut this recently is not restored yet, so one quiet window does not undo a cut at once.
    "recovery_hold_seconds": 30,
    # Latency samples kept per scope and window (reservoir sampling beyond it).
    "max_latency_samples": 500,
    # Each process re-reads the policies and Smart factors at most this often (and at once after a local save).
    "state_refresh_seconds": 10,
}

ADMISSION = {
    # Concurrent requests one process accepts (uvicorn --limit-concurrency answers 503 beyond it).
    "concurrency_limit": _env_int("UVICORN_LIMIT_CONCURRENCY", 20),
    # Slots only P0 may use, whatever the tier shares say.
    "p0_reserved_slots": 2,
    # Retry-After (seconds) when a request is refused for lack of a slot of its tier.
    "retry_after_seconds": 2,
}

ABUSE = {
    # Refusals (429, from this limiter or from the view's own limits) one caller collects within this window...
    "strike_window_seconds": 300,
    # ...this many of them block the caller for the scope...
    "strikes_to_block": 10,
    # ...for this long, doubling with each block within level_memory_seconds, up to the maximum.
    "block_base_seconds": 30,
    "block_max_seconds": 900,
    "level_memory_seconds": 3_600,
}

STORE = {
    # "auto": a shared atomic counter when the default cache is one of shared_backends (Redis), else per process.
    # "shared" or "local" force one.
    "mode": "auto",
    "shared_backends": ("django.core.cache.backends.redis.RedisCache", "django_redis.cache.RedisCache"),
    # Per-process mode: each process writes its heartbeat row at most this often...
    "heartbeat_seconds": 30,
    # ...a row not refreshed for this long no longer counts as a live process...
    "process_expiry_seconds": 90,
    # ...and is deleted after this long.
    "process_prune_seconds": 86_400,
}

FALLBACK = {
    # Routes no table or view names: CLI and admin by path, the rest by method and sign-in.
    "cli_prefix": "/admin-api/",
    "admin_prefix": "/admin/",
    "cli": "cli",
    "admin": "staff-admin",
    "public_read": "public-read",
    "public_write": "public-write",
    "member_read": "member-read",
    "member_write": "member-write",
    # Requests for a path no route matches.
    "not_found": "not-found",
}
