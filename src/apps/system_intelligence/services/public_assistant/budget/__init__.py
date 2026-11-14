"""Token budgeting for the public assistant and the past-project AI search.

Two budgets are charged for every model call, and a request is admitted only
when it fits both:

* a per-ACTOR budget -- one visitor, one member, or the shared ``legacy`` bucket
  (see ``chat/actors.py``; its row is charged like any other but carries no limit).
  Never the client IP: the whole campus shares one public address, so an IP key
  would be a single bucket for everybody.
* a GLOBAL budget for the FEATURE being used -- one row for the public
  assistant and one for AI search, each limited by
  ``SystemIntelligenceConfig.public_assistant_global_token_limit``. Visitor
  identities are free to obtain, so this is the real spend ceiling. The two
  rows are separate so that draining one feature (the anonymous chat can be
  scripted) can never pause the other (the members' AI search).

Backends: Redis is used when configured. Production environments without Redis
use a transactional database counter -- this is the authoritative path, the
only one that is atomic across web workers and ECS tasks -- while
tests/development may explicitly opt in to the local cache fallback. Budget
rows are keyed by an opaque 64-hex value; no IP and no raw id is stored.
"""

from .cache_store import (
    _release_cache_reservation_quietly,
    _reserve_cache_budget,
    _settle_cache_reservations,
    _shared_redis_client,
)
from .counters import (
    check_budget,
    client_ip,
    global_budget_usage,
    global_tokens_used,
    hash_ip,
    record_usage,
    tokens_used,
)
from .database_store import _record_database_usage, _reserve_database_budget, _settle_database_reservation
from .limits import (
    _DEFAULT_WINDOW_SECONDS,
    FEATURE_AI_SEARCH,
    FEATURE_ASSISTANT,
    GLOBAL_BUDGET_KEYS,
    GLOBAL_FEATURE_LABELS,
    GLOBAL_WINDOW_SECONDS,
    BudgetBackendUnavailable,
    BudgetReservation,
    GlobalBudgetUsage,
    _budget_window_key,
    _new_window_id,
    _warn_global_budget_exhausted,
    budget_key,
    global_budget_key,
)
from .redis_scripts import _RECONCILE_SCRIPT, _RELEASE_SCRIPT, _RESERVE_SCRIPT
from .reservations import (
    _database_budget_enabled,
    _reserve_cache_pair,
    reconcile_budget,
    release_budget,
    reserve_budget,
)
from .retention import purge_expired_public_assistant_budgets
from .usage import MAX_REPORTED_TOKENS, _reconciled_tokens, reported_total_tokens, sanitized_usage

__all__ = [
    "FEATURE_AI_SEARCH",
    "FEATURE_ASSISTANT",
    "GLOBAL_BUDGET_KEYS",
    "GLOBAL_FEATURE_LABELS",
    "GLOBAL_WINDOW_SECONDS",
    "MAX_REPORTED_TOKENS",
    "BudgetBackendUnavailable",
    "BudgetReservation",
    "GlobalBudgetUsage",
    "budget_key",
    "check_budget",
    "client_ip",
    "global_budget_key",
    "global_budget_usage",
    "global_tokens_used",
    "hash_ip",
    "purge_expired_public_assistant_budgets",
    "reconcile_budget",
    "record_usage",
    "release_budget",
    "reported_total_tokens",
    "reserve_budget",
    "sanitized_usage",
    "tokens_used",
]
