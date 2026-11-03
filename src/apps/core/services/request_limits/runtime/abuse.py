"""Per-caller abuse escalation: priority is not an exemption from abuse protection.

A **strike** is a refusal of the caller's own making, never of everyone's: going over its own limit or its source's
flood ceiling (at the scope's full size, not just a Smart cut), or a 429 from the view's own limit (a code cooldown,
an hourly cap, the SMS budget, the sign-in lockout) for a caller with its own key, not a shared IP. Refusals for the
aggregate cap, for want of a concurrency slot and during a block are no strikes (``limiter`` decides). After
``strikes_to_block`` strikes within ``strike_window_seconds`` the caller is blocked for the scope for
``block_base_seconds``, doubling with every further block within ``level_memory_seconds``, up to
``block_max_seconds``; a block always ends, however much the caller keeps sending. So a P0 caller pumping SMS or
guessing codes ends up blocked like any other.
"""

import math

from . import store
from .context import section


def _names(scope: str, identity: str) -> tuple[str, str, str]:
    """The strike bucket, and the cache keys of the block level and the block's end."""
    return f"strikes|{scope}|{identity}", store.key("level", scope, identity), store.key("block", scope, identity)


def blocked_for(scope: str, identity: str | None, now: float) -> int | None:
    """Seconds the caller stays blocked for ``scope``, or None."""
    if identity is None:
        return None
    until = store.get(_names(scope, identity)[2])
    if not isinstance(until, int | float) or until <= now:
        return None
    return max(1, math.ceil(until - now))


def strike(scope: str, identity: str | None, now: float) -> int | None:
    """Count one strike; return the block (seconds) it started, or None. A caller blocked already is not struck:
    its refusals during the block never lengthen it."""
    if identity is None or blocked_for(scope, identity, now) is not None:
        return None
    abuse = section("abuse")
    strikes, level, block = _names(scope, identity)
    window = abuse["strike_window_seconds"]
    if store.hit(strikes, window, now) < abuse["strikes_to_block"]:
        return None
    store.delete(store.window_key(strikes, window, now))
    previous = store.get(level)
    blocks = (previous if isinstance(previous, int) else 0) + 1
    store.put(level, blocks, abuse["level_memory_seconds"])
    seconds = min(abuse["block_max_seconds"], abuse["block_base_seconds"] * 2 ** (blocks - 1))
    store.put(block, now + seconds, seconds)
    return math.ceil(seconds)
