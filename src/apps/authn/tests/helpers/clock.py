"""A settable clock for tests of windowed counters (the login lockout).

``apps.authn.services.login_guard`` reads ``time.time`` for its window indexes and expiry times (as do the cache
backends for entry expiry), so patching it moves them together. The default start sits one minute into a 15-minute
window of a UTC day, so the windows end at known offsets: 14 minutes ahead (short window), 4 minutes ahead
(the 5-minute spray-detection window) and ``SECONDS_LEFT_IN_DAY`` ahead (daily window).
"""

from unittest.mock import patch

DAY_START = 1_790_035_200  # a UTC midnight (divisible by 86400), September 2026
SECONDS_PER_DAY = 86_400
START = DAY_START + 3 * 3600 + 60  # 03:01 UTC
SECONDS_LEFT_IN_SHORT_WINDOW = 14 * 60  # the 15-minute window that contains START ends at 03:15
SECONDS_LEFT_IN_SPRAY_WINDOW = 4 * 60  # the 5-minute window that contains START ends at 03:05
SECONDS_LEFT_IN_DAY = SECONDS_PER_DAY - (START - DAY_START)


class FrozenClock:
    """Callable stand-in for ``time.time`` that only moves when told to."""

    def __init__(self, now: float = START):
        self.now = float(now)

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def freeze_time(test_case, now: float = START) -> FrozenClock:
    """Patch ``time.time`` to a ``FrozenClock`` for the rest of ``test_case`` and return it."""
    clock = FrozenClock(now)
    patcher = patch("time.time", clock)
    patcher.start()
    test_case.addCleanup(patcher.stop)
    return clock
