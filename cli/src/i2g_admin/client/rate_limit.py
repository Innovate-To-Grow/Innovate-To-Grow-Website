"""Waiting out 429 Too Many Requests.

The server refuses a request with 429 before running it (its request limiter answers ahead of the view), so a refused
read, or a refused OAuth token exchange whose authorization code was therefore never used, is safe to send again.
The CLI waits as long as the server asks (``Retry-After``, else the JSON body's ``retry_after``, else a doubling
fallback), plus a little jitter so parallel runs refused together do not come back together, and sends the request
again, at most ``RATE_LIMIT_RETRIES`` times. A wait longer than ``MAX_RATE_LIMIT_WAIT`` is not waited out: the 429
is returned at once and surfaces with the server's message.

This applies whatever ``--max-attempts`` says: that option governs transient failures (5xx, dropped connections),
while being told to slow down is not a failure of the request.
"""

import random
import time
from email.utils import parsedate_to_datetime

# How many times one refused request is sent again.
RATE_LIMIT_RETRIES = 3
# The longest wait (seconds) the CLI sits out; a longer Retry-After fails the request at once.
MAX_RATE_LIMIT_WAIT = 60.0
# The wait when a 429 names none: RATE_LIMIT_FALLBACK * 2**(n-1) seconds before the n-th resend.
RATE_LIMIT_FALLBACK = 1.0
# Up to this many seconds of random jitter are added to every wait.
RATE_LIMIT_JITTER = 0.5


def parse_retry_after(value):
    """Return a non-negative delay in seconds from a ``Retry-After`` header value.

    Accepts either an integer number of seconds or an HTTP-date; returns ``None``
    when the value is missing or unparseable so the caller falls back to backoff.
    """
    if not value:
        return None
    value = value.strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, when.timestamp() - time.time())


def requested_wait(response):
    """The seconds a 429 asks the client to wait: its Retry-After header, else the body's retry_after; or None."""
    seconds = parse_retry_after(response.headers.get("Retry-After"))
    if seconds is not None:
        return seconds
    try:
        payload = response.json()
    except ValueError:
        return None
    value = payload.get("retry_after") if isinstance(payload, dict) else None
    if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
        return None
    return float(value)


def rate_limit_wait(response, refusal, max_wait=MAX_RATE_LIMIT_WAIT):
    """Seconds to sleep before resending after the ``refusal``-th 429 in a row, or None to give up now."""
    seconds = requested_wait(response)
    if seconds is None:
        seconds = RATE_LIMIT_FALLBACK * 2 ** (refusal - 1)
    if seconds > max_wait:
        return None
    return seconds + random.random() * RATE_LIMIT_JITTER  # noqa: S311 — jitter, not security-sensitive


def send_with_rate_limit_retries(send, retries=RATE_LIMIT_RETRIES, max_wait=MAX_RATE_LIMIT_WAIT):
    """Call ``send()`` (one HTTP request returning a response) again after each 429 asking for at most ``max_wait``
    seconds, up to ``retries`` times; return the last response."""
    response = send()
    for refusal in range(1, retries + 1):
        if response.status_code != 429:
            return response
        wait = rate_limit_wait(response, refusal, max_wait)
        if wait is None:
            return response
        time.sleep(wait)
        response = send()
    return response


def wait_hint(response):
    """`` Try again in N seconds.`` for a 429 that names its wait, else an empty string."""
    seconds = requested_wait(response)
    if seconds is None:
        return ""
    whole = max(1, int(-(-seconds // 1)))
    return f" Try again in {whole} second{'s' if whole != 1 else ''}."
