"""Reading the provider's reported token usage safely."""

import logging
from collections.abc import Mapping

from .limits import BudgetReservation

logger = logging.getLogger("apps.system_intelligence.services.public_assistant.budget")

# No single model call can cost this much (requests are capped far below it). A larger reported number is a
# provider or parsing fault, and storing it would overflow the counters, so it is treated as unreadable.
MAX_REPORTED_TOKENS = 10_000_000
_USAGE_KEYS = ("inputTokens", "outputTokens", "totalTokens")


def _token_count(value) -> int | None:
    """``value`` as a plausible token count, or ``None`` when it is not one (text, NaN, infinity, absurd size)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if 0 <= number <= MAX_REPORTED_TOKENS else None


def reported_total_tokens(usage):
    """The provider's ``totalTokens`` exactly as reported, for :func:`reconcile_budget`.

    A usage block that is not a mapping is passed through as is, so that reconciliation sees it is unreadable
    and settles the call at the reserved amount instead of charging nothing.
    """
    if isinstance(usage, Mapping):
        return usage.get("totalTokens") or 0
    return usage or 0


def sanitized_usage(usage) -> dict[str, int]:
    """The provider's usage block reduced to plausible token counts.

    This is what gets stored in the audit log and returned to the caller: the raw block is provider-controlled,
    and a non-finite number in it cannot be serialised as JSON.
    """
    if not isinstance(usage, Mapping):
        return {}
    clean = {}
    for key in _USAGE_KEYS:
        count = _token_count(usage.get(key))
        if count is not None:
            clean[key] = count
    return clean


def _reconciled_tokens(reservation: BudgetReservation, actual_tokens) -> int:
    """The provider's reported usage as a non-negative integer.

    The value comes from the provider's usage block. If it cannot be read as a
    plausible token count, the reservation is settled at the amount it reserved
    (estimated input plus the output cap): the budgets stay charged for the call,
    the reservation records are consumed, and the request is still answered.
    """
    if not actual_tokens and not isinstance(actual_tokens, bool):
        return 0
    try:
        number = int(actual_tokens)
    except (TypeError, ValueError, OverflowError):
        number = None
    if number is not None and number < 0:
        return 0
    if number is None or number > MAX_REPORTED_TOKENS or isinstance(actual_tokens, bool):
        logger.warning(
            "Unparsable provider token usage %.80r: charging the reserved %s tokens instead",
            actual_tokens,
            reservation.reserved_tokens,
        )
        return reservation.reserved_tokens
    return number
