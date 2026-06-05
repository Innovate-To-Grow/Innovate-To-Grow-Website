import random
import time
from email.utils import parsedate_to_datetime

import requests

from .config import validate_base_url
from .errors import ApiError, AuthError

# (connect, read) timeout so a hung server can never block the CLI indefinitely.
REQUEST_TIMEOUT = (5, 30)
# Transient statuses U5 retries; declared here so the seam is visible from U1.
RETRY_STATUSES = (429, 500, 502, 503, 504)
# Only retry HTTP methods with no side effects on the server. A non-idempotent
# write (POST/PATCH/DELETE) that times out or returns 5xx may already have been
# committed; resending it would silently duplicate the row on models without a
# unique constraint, so we never retry those — a single failure is surfaced as-is.
IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
# Exponential-backoff knobs (seconds). The computed delay is
# ``BACKOFF_BASE * 2**(attempt-1)`` capped at ``BACKOFF_MAX``, then multiplied by
# a uniform random factor in [0, 1) (AWS-style "full jitter").
BACKOFF_BASE = 0.5
BACKOFF_MAX = 20.0
# Hard ceiling on any single sleep, including a server-supplied ``Retry-After``.
# A buggy/hostile upstream could otherwise send ``Retry-After: inf`` (or a
# far-future date) and make the CLI block effectively forever.
MAX_RETRY_SLEEP = 60.0


def _parse_retry_after(value):
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


class ApiClient:
    """Thin wrapper over a requests.Session with a bearer header and status→error mapping.

    The ``timeout`` / ``max_attempts`` / ``retry_statuses`` knobs are accepted now
    (with today's behavior as defaults: a single attempt) so U5 can implement
    retry/backoff inside ``_send`` without changing this signature or any caller.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout=REQUEST_TIMEOUT,
        max_attempts: int = 1,
        retry_statuses=RETRY_STATUSES,
    ):
        validate_base_url(base_url)
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        # At least one attempt; a non-positive value would otherwise skip the request entirely.
        self.max_attempts = max(1, max_attempts)
        self.retry_statuses = tuple(retry_statuses)
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"

    def _backoff_delay(self, attempt):
        """Exponential backoff with full jitter for the given 1-based attempt number."""
        ceiling = min(BACKOFF_BASE * 2 ** (attempt - 1), BACKOFF_MAX)
        return random.random() * ceiling  # noqa: S311 — jitter, not security-sensitive

    def _sleep_before_retry(self, attempt, response):
        """Sleep before the next attempt, honoring ``Retry-After`` when larger than backoff.

        Both the backoff and any server-supplied ``Retry-After`` are clamped to
        ``MAX_RETRY_SLEEP`` so a hostile/buggy upstream can never make the CLI
        block for an unbounded duration.
        """
        delay = self._backoff_delay(attempt)
        if response is not None:
            retry_after = _parse_retry_after(response.headers.get("Retry-After"))
            if retry_after is not None:
                delay = max(delay, retry_after)
        time.sleep(min(delay, MAX_RETRY_SLEEP))

    def _send(self, method, url, *, params=None, json_body=None, headers=None):
        """Issue the request, retrying transient failures up to ``self.max_attempts`` times.

        A response whose status is in ``self.retry_statuses`` or a transient
        :class:`requests.RequestException` triggers a retry while attempts remain;
        the last response is returned (or the last exception re-raised) once they
        run out. With ``max_attempts == 1`` this performs exactly one request and
        never sleeps, matching the pre-U5 behavior.

        Retries apply only to idempotent methods (see ``IDEMPOTENT_METHODS``).
        Non-idempotent writes are sent exactly once regardless of ``max_attempts``
        so a 5xx/timeout after the server already committed can't duplicate the row.
        """
        attempts = self.max_attempts if method.upper() in IDEMPOTENT_METHODS else 1
        for attempt in range(1, attempts + 1):
            last_attempt = attempt >= attempts
            try:
                response = self.session.request(
                    method, url, params=params, json=json_body, headers=headers, timeout=self.timeout
                )
            except requests.RequestException:
                if last_attempt:
                    raise
                self._sleep_before_retry(attempt, None)
                continue
            if last_attempt or response.status_code not in self.retry_statuses:
                return response
            self._sleep_before_retry(attempt, response)

    def request(self, method, path, *, params=None, json_body=None, headers=None):
        response = self._send(method, f"{self.base_url}{path}", params=params, json_body=json_body, headers=headers)
        return self._handle(response)

    @staticmethod
    def _handle(response):
        if response.status_code == 401:
            raise AuthError("Token expired or invalid. Run `i2g-admin login`.")
        if response.status_code == 204:
            return None
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if response.status_code >= 400:
            detail = payload.get("detail") if isinstance(payload, dict) else None
            raise ApiError(response.status_code, detail or f"Request failed ({response.status_code}).", payload)
        return payload

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path, **kwargs):
        return self.request("POST", path, **kwargs)

    def patch(self, path, **kwargs):
        return self.request("PATCH", path, **kwargs)

    def delete(self, path, **kwargs):
        return self.request("DELETE", path, **kwargs)
