"""Where a sender runs decides how long it may wait for a slot (``DELIVERY_RATES["waits"]``); and the clock and
sleep every limiter module uses (through this module, so tests can drive time without sleeping).

The wait mode is a context variable: the background worker and the in-process campaign threads set it around
their work, request handlers keep the default (inline). It only chooses the wait cap; the lane (transactional or
bulk) is always passed to ``admit`` explicitly. A new thread starts in the default mode.
"""

import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from enum import StrEnum

from django.utils import timezone

from ..rules.defaults import section

clock = timezone.now
sleep = time.sleep


class WaitMode(StrEnum):
    INLINE = "inline"
    READ = "read"
    WORKER = "worker"
    DEDICATED = "dedicated"


_SETTING = {
    WaitMode.INLINE: "inline_seconds",
    WaitMode.READ: "read_seconds",
    WaitMode.WORKER: "worker_seconds",
    WaitMode.DEDICATED: "dedicated_seconds",
}
_MODE: ContextVar[WaitMode] = ContextVar("delivery_rates_wait_mode", default=WaitMode.INLINE)


@contextmanager
def wait_mode(mode: WaitMode | str) -> Iterator[WaitMode]:
    token = _MODE.set(WaitMode(mode))
    try:
        yield _MODE.get()
    finally:
        _MODE.reset(token)


def current_wait_mode() -> WaitMode:
    return _MODE.get()


def wait_cap(mode: WaitMode | str | None = None) -> float:
    """Longest wait, in seconds, for a slot in ``mode`` (default: the current mode)."""
    return float(section("waits")[_SETTING[WaitMode(mode) if mode else current_wait_mode()]])
