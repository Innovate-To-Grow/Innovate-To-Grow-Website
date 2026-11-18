"""The Message Trace sync's ``EMAIL_MONITORING`` values, each kept within safe bounds whatever the settings hold."""

from django.conf import settings

# Graph keeps message traces for 90 days; a longer give-up time would only ask for nothing.
MAX_TRACE_AGE_HOURS = 90 * 24


def _value(name: str, low: int, high: int | None = None) -> int:
    value = max(low, int(settings.EMAIL_MONITORING[name]))
    return value if high is None else min(value, high)


def interval_seconds() -> int:
    """Seconds between two syncs: ``trace_interval_seconds``, never under five minutes."""
    return _value("trace_interval_seconds", 300)


def max_requests_per_run() -> int:
    """Graph requests one sync may make: ``trace_max_requests_per_run``, one to fifty."""
    return _value("trace_max_requests_per_run", 1, 50)


def page_size() -> int:
    """Rows asked per request (``$top``): ``trace_page_size``, 1 to 5000 (Graph's own bounds)."""
    return _value("trace_page_size", 1, 5000)


def max_bytes() -> int:
    """Most bytes read of one response: ``trace_max_bytes``, 64 KiB to 32 MiB."""
    return _value("trace_max_bytes", 64 * 1024, 32 * 1024 * 1024)


def min_age_minutes() -> int:
    """Minutes after acceptance before an email is first traced: ``trace_min_age_minutes``, one at least."""
    return _value("trace_min_age_minutes", 1)


def give_up_hours() -> int:
    """Hours after acceptance an email is no longer traced: ``trace_give_up_hours``, always past the minimum age and
    within Graph's 90-day trace retention."""
    floor = min_age_minutes() // 60 + 1
    return _value("trace_give_up_hours", floor, MAX_TRACE_AGE_HOURS)
