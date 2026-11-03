"""Recent refusals (429 answers) per route scope, for the admin page.

Each 429 is counted in a one-minute bucket of the counter store, split by who refused it: this limiter (a per-caller
or aggregate limit, an abuse block, no slot for the tier) or the view's own finer limit (a code cooldown, an hourly
cap, the sign-in lockout). With a shared store the counts are site-wide; with per-process counters they are the
counts of the process that answers the admin page. One cache call per 429 and nothing per served request; the
buckets expire after ``store.refusal_history_minutes``.
"""

import math

from . import store
from .context import section

BUCKET_SECONDS = 60
LIMITER = "limiter"
VIEW = "view"
KINDS = (LIMITER, VIEW)


def _bucket(scope: str, kind: str) -> str:
    return f"refused|{kind}|{scope}"


def history_minutes() -> int:
    return section("store")["refusal_history_minutes"]


def count(scope: str, now: float, *, by_limiter: bool) -> None:
    """Count one 429 of ``scope``: refused by this limiter (``by_limiter``) or by the view's own limit."""
    kind = LIMITER if by_limiter else VIEW
    keep = (history_minutes() + 1) * BUCKET_SECONDS
    store.hit(_bucket(scope, kind), BUCKET_SECONDS, now, keep=keep)


def recent(scopes, now: float) -> dict[str, dict[str, int]]:
    """Per scope, the 429s of the last ``refusal_history_minutes`` (the current minute included), by kind."""
    minutes = history_minutes()
    first = math.floor(now / BUCKET_SECONDS) - minutes + 1
    names = {}
    for scope in scopes:
        for kind in KINDS:
            for minute in range(first, first + minutes):
                name = store.window_key(_bucket(scope, kind), BUCKET_SECONDS, minute * BUCKET_SECONDS)
                names[name] = (scope, kind)
    found = store.get_many(list(names))
    totals = {scope: dict.fromkeys(KINDS, 0) for scope in scopes}
    for name, value in found.items():
        if name in names and isinstance(value, int) and not isinstance(value, bool):
            scope, kind = names[name]
            totals[scope][kind] += value
    return totals
