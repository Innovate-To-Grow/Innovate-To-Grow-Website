"""What ``REQUEST_RATE_LIMITS`` may hold: its sections and keys, the tier order and identities, and the bounds of
the policy columns."""

import re

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
