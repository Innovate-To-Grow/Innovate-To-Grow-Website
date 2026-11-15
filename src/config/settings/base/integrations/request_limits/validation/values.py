"""Checking one value: a count, fraction, number of seconds, flag or text, a mapping's keys, and an ordering."""

import math

from django.core.exceptions import ImproperlyConfigured

from .schema import MAX_COUNT, MAX_SECONDS


def _fail(path, problem):
    raise ImproperlyConfigured(f"REQUEST_RATE_LIMITS {'.'.join(str(part) for part in path)} {problem}.")


def _number(value) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def _count(path, value, low=1, high=MAX_COUNT):
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        _fail(path, f"must be a whole number between {low} and {high}")


def _fraction(path, value, *, below_one=False):
    if not _number(value) or not 0 < value <= 1 or (below_one and value >= 1):
        _fail(path, "must be a share greater than 0 and " + ("below 1" if below_one else "at most 1"))


def _seconds(path, value, low=0.0):
    if not _number(value) or not low < value <= MAX_SECONDS:
        _fail(path, f"must be a number of seconds above {low:g} and at most {MAX_SECONDS}")


def _bool(path, value):
    if not isinstance(value, bool):
        _fail(path, "must be true or false")


def _text(path, value, *, blank=False):
    if not isinstance(value, str) or (not blank and not value.strip()):
        _fail(path, "must be " + ("text" if blank else "non-empty text"))


def _keys(path, values, required):
    if not isinstance(values, dict):
        _fail(path, "must be an object")
    if set(values) != set(required):
        _fail(path, f"must have exactly the keys {', '.join(required)}")


def _below(path, low, high, problem):
    if low >= high:
        _fail(path, problem)
