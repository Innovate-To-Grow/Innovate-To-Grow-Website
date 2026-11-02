"""Per-caller abuse escalation: priority is not an exemption from abuse protection.

Every 429 one caller (an identity, never "everyone") collects in a scope is a strike — whether this limiter refused
it or the view's own limit did (a code cooldown, an hourly cap, the SMS budget, the sign-in lockout). After
``strikes_to_block`` strikes within ``strike_window_seconds`` the caller is blocked for the scope for
``block_base_seconds``, doubling with every further block within ``level_memory_seconds``, up to
``block_max_seconds``. So a P0 caller pumping SMS or guessing codes ends up blocked like any other.
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
    """Count one refusal; return the block (seconds) it started, or None."""
    if identity is None:
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
