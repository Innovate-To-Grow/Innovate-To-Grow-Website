"""Per-destination code-guess degradation (email and SMS verification codes).

A code is 6 digits. Each destination can be sent a bounded number of codes an hour (``MAX_CHALLENGES_PER_HOUR``
per purpose for email, ``MAX_SENDS_PER_HOUR`` for SMS) and each code normally allows ``max_attempts`` guesses, so
an attacker hammering one destination gets about ``10 x 5 = 50`` guesses an hour. Once a destination has collected
``FAILURE_THRESHOLD`` failed guesses within ``FAILURE_WINDOW``, every code NEWLY issued to it allows a single guess,
which caps the attacker at one guess per code sent (the hourly send cap).

Deliberately keyed on the destination only, never on the client IP (the campus shares one address), and never a
lock: the owner still receives codes and a correct first try still verifies. Codes already issued keep their own
limit. No answer is added or changed: code requests answer exactly as before (the limit is never exposed), and the
wrong guess that spends a degraded code gets the plain invalid answer, for email and for SMS alike: exactly what a
first wrong guess gets on any other destination. (A normal SMS code still answers "throttled" on its fifth wrong
guess; a degraded one never reaches a fifth, so that answer is not what gives the degradation away.)

Failures are the ``attempts`` counters of the existing challenge rows (only a wrong guess increments them; a
successful check does not), counted by issue time: a guess can only land within the code's TTL (10 minutes) of its
issue, so this is the rolling window to within that TTL. No model change: the counts come from existing rows.
"""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Sum

from apps.authn.models.security import EmailAuthChallenge

FAILURE_THRESHOLD = 10
FAILURE_WINDOW = timedelta(hours=24)
DEGRADED_MAX_ATTEMPTS = 1


def max_attempts_for(recent_failures: int, default: int) -> int:
    """``max_attempts`` for a new challenge, given the destination's failed guesses in ``FAILURE_WINDOW``."""
    return DEGRADED_MAX_ATTEMPTS if recent_failures >= FAILURE_THRESHOLD else default


def recent_email_failures(target_email: str, *, now) -> int:
    """Failed code guesses against ``target_email`` (already normalised) over the last ``FAILURE_WINDOW``.

    One aggregate query. ``purpose IN (every purpose)`` filters nothing, but it lets PostgreSQL drive the scan with
    the ``(purpose, target_email, status)`` index (one probe per purpose) instead of a sequential scan; there is no
    index led by ``target_email``. Rows store the normalised address, so an exact match is used (``iexact`` would
    wrap the column in ``UPPER()`` and defeat the index).
    """
    total = EmailAuthChallenge.objects.filter(
        purpose__in=EmailAuthChallenge.Purpose.values,
        target_email=target_email,
        created_at__gte=now - FAILURE_WINDOW,
    ).aggregate(total=Sum("attempts"))["total"]
    return int(total or 0)
