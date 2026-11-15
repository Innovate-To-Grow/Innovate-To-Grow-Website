"""How long handing a code to the SMS provider takes, so that a withheld code takes about as long to "send".

A phone sign-in for a number that may not sign in (saved on an account but not verified) is answered exactly like a
real send, but nothing is sent (``start_phone_verification(..., deliver=False)``). Its answer must not come back
noticeably sooner than a real one, or the response time alone would tell the number apart. So every provider call
that delivered a code records how long it took (``observe_send``), and a withheld code waits for one of those
durations, picked at random (``wait_like_a_send``): the withheld answers then take as long as the real ones do.

The durations are this process's own recent sends. Until it has sent any, the wait is drawn from
``settings.SMS_WITHHELD_SEND_DELAY_SECONDS``, a ``(low, high)`` range in seconds.

The wait goes through the delivery-rate limiter's ``sleep`` (``core.services.delivery_rates.runtime.context``), which
the test runner replaces with its virtual clock, so no test ever waits for real.
"""

from __future__ import annotations

import secrets
import threading
from collections import deque

from django.conf import settings

from apps.core.services.delivery_rates.runtime import context

# The durations kept: enough to follow the provider's usual spread, few enough to follow a change in it quickly.
SAMPLE_SIZE = 50
# Used only when the setting is missing or malformed: the usual time of one SendTextMessage call, connection included.
DEFAULT_DELAY_RANGE = (0.2, 0.6)

_samples: deque[float] = deque(maxlen=SAMPLE_SIZE)
_lock = threading.Lock()
_random = secrets.SystemRandom()


def observe_send(seconds: float) -> None:
    """Record how long one provider call that delivered a code took."""
    if seconds >= 0:
        with _lock:
            _samples.append(float(seconds))


def _fallback_range() -> tuple[float, float]:
    configured = getattr(settings, "SMS_WITHHELD_SEND_DELAY_SECONDS", DEFAULT_DELAY_RANGE)
    try:
        low, high = (float(value) for value in configured)
    except (TypeError, ValueError):
        return DEFAULT_DELAY_RANGE
    if low < 0 or high < low:
        return DEFAULT_DELAY_RANGE
    return low, high


def send_delay() -> float:
    """A provider-call duration: one of this process's recent sends, or one drawn from the configured range."""
    with _lock:
        observed = list(_samples)
    if observed:
        return _random.choice(observed)
    low, high = _fallback_range()
    return _random.uniform(low, high)


def wait_like_a_send() -> None:
    """Wait about as long as handing a code to the provider takes."""
    context.sleep(send_delay())


def reset() -> None:
    """Forget the recorded durations (tests)."""
    with _lock:
        _samples.clear()
