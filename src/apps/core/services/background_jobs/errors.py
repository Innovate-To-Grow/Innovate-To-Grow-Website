"""What a job handler raises to steer the worker: retry, wait for its delivery slot, fail, or hold for review."""

import math
import re
from datetime import datetime

from django.db import OperationalError
from django.utils import timezone
from gspread.exceptions import APIError as GspreadAPIError

_ERROR_MAX_LENGTH = 500
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


class TransientJobError(RuntimeError):
    """A known temporary failure that is safe to retry."""

    def __init__(self, message: str = "", *, retry_after: float | None = None):
        super().__init__(message)
        # Seconds the provider asked us to wait (an HTTP Retry-After); the retry is never scheduled sooner.
        self.retry_after = retry_after


class DeferredJobError(TransientJobError):
    """The delivery limiter held the job back before any provider call: certainly not sent.

    The job runs again at ``until`` without using up an attempt, however long the lane stays paced or stopped.
    """

    def __init__(self, message: str = "", *, until: datetime):
        seconds = max(0, math.ceil((until - timezone.now()).total_seconds()))
        super().__init__(message or f"Waiting for a delivery slot (about {seconds} s).", retry_after=seconds)
        self.until = until


class PermanentJobError(RuntimeError):
    """A definitive failure that must not be retried automatically."""


class UncertainJobError(RuntimeError):
    """A provider call may have succeeded and must be reviewed manually."""


class JobClaimLost(RuntimeError):
    """The worker no longer owns a job and must not call an external provider."""


def safe_error(exc: BaseException) -> str:
    text = _CONTROL_RE.sub(" ", str(exc)).strip()
    return (text or exc.__class__.__name__)[:_ERROR_MAX_LENGTH]


def exception_chain(exc: BaseException):
    seen = set()
    current = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


_TRANSIENT_NAMES = frozenset(
    {
        "ConnectTimeout",
        "ConnectionClosedError",
        "ConnectionError",
        "EndpointConnectionError",
        "ReadTimeout",
        "ReadTimeoutError",
        "ServiceUnavailable",
        "ThrottlingException",
        "Timeout",
    }
)


def is_known_transient(exc: BaseException) -> bool:
    for item in exception_chain(exc):
        if (
            isinstance(item, TransientJobError | OperationalError | TimeoutError | ConnectionError)
            or item.__class__.__name__ in _TRANSIENT_NAMES
        ):
            return True
        if isinstance(item, GspreadAPIError):
            status_code = getattr(getattr(item, "response", None), "status_code", None)
            if status_code in {408, 429} or (isinstance(status_code, int) and 500 <= status_code <= 599):
                return True
    return False
