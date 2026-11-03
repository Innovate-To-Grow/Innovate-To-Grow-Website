"""The clock every request-limit module reads (through this module, so tests can drive time) and the settings."""

import time
from datetime import UTC, datetime

from django.conf import settings

clock = time.time


def section(name: str) -> dict:
    """One section of ``REQUEST_RATE_LIMITS``, read at call time (``override_settings`` applies)."""
    return settings.REQUEST_RATE_LIMITS[name]


def as_datetime(seconds: float) -> datetime:
    return datetime.fromtimestamp(seconds, UTC)


def as_seconds(moment: datetime | None) -> float | None:
    return None if moment is None else moment.timestamp()
