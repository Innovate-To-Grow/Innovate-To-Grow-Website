"""The request path: ``admit`` before the view runs, ``finish`` after it answered.

``admit`` classifies the request, then refuses it (429 with Retry-After) when its caller is blocked for the scope
(abuse escalation), over the per-caller limit, over the scope's aggregate cap, or — last, so a refused request never
holds a slot — when its tier has no concurrency slot left. ``finish`` frees the slot, records the signals Smart
limiting reads, counts a 429 as a strike against the caller (whoever refused it) and in the admin's recent
refusals, and lets the controller assess a window that just ended. Requests for paths no route matches are limited
afterwards in the ``not-found`` scope.
"""

import math
from dataclasses import dataclass

from django.http import JsonResponse

from . import identity, scopes
from .rules.limits import effective_limits
from .runtime import abuse, context, heartbeat, refusals, registry, signals, smart, store
from .runtime.context import section

RATE_LIMITED = "rate_limited"


@dataclass
class Mark:
    """What ``admit`` decided, kept on the request for ``finish``."""

    scope: str
    tier: str
    key: str | None
    started: float
    admitted: bool = False
    refused: bool = False


def rejection(seconds: float) -> JsonResponse:
    """The 429 answer: ``{"detail", "code": "rate_limited", "retry_after"}`` and the Retry-After header."""
    wait = max(1, math.ceil(seconds))
    unit = "second" if wait == 1 else "seconds"
    response = JsonResponse(
        {"detail": f"Too many requests. Please try again in {wait} {unit}.", "code": RATE_LIMITED, "retry_after": wait},
        status=429,
    )
    response["Retry-After"] = str(wait)
    response["Cache-Control"] = "no-store"
    return response


def live_processes(now: float) -> int:
    """How many processes share each limit: 1 with a shared counter store."""
    return 1 if store.mode() == store.SHARED else heartbeat.live_processes(now)


def _over_limit(config, key: str | None, now: float) -> int | None:
    """Count the request; the seconds until its window resets when it is over a limit, else None."""
    limits = effective_limits(config, live_processes(now))
    reset = store.window_reset(limits.period, now)
    if key is not None and store.hit(f"{config.scope}|{key}", limits.period, now) > limits.per_identity:
        return reset
    if limits.global_cap is not None and store.hit(f"{config.scope}|*", limits.period, now) > limits.global_cap:
        return reset
    return None


def admit(request, view_func):
    """None to let the request through, or the 429 response."""
    now = context.clock()
    found = scopes.classify(request, view_func)
    if found.scope is None:
        return None
    config = registry.configs(now).get(found.scope)
    if config is None or not config.enabled:
        return None
    key = identity.bucket_key(request, config.scope, config.identity)
    mark = Mark(config.scope, config.tier, key, now)
    request._request_limit = mark
    retry = abuse.blocked_for(config.scope, key, now) or _over_limit(config, key, now)
    if retry is None:
        if signals.admit(config.tier, now):
            mark.admitted = True
            return None
        retry = section("admission")["retry_after_seconds"]
    mark.refused = True
    return rejection(retry)


def _not_found(request, response, now: float):
    if (
        getattr(request, "resolver_match", None) is not None
        or response.status_code != 404
        or request.method == "OPTIONS"
    ):
        return response
    scope = section("fallback")["not_found"]
    config = registry.configs(now).get(scope)
    if config is None or not config.enabled:
        return response
    key = identity.bucket_key(request, scope, config.identity)
    retry = abuse.blocked_for(scope, key, now) or _over_limit(config, key, now)
    if retry is None:
        return response
    signals.record(scope, 429, 0.0, now, served=False)
    refusals.count(scope, now, by_limiter=True)
    abuse.strike(scope, key, now)
    return rejection(retry)


def release(request) -> None:
    """Give back the request's slot (once)."""
    mark = getattr(request, "_request_limit", None)
    if mark is not None and mark.admitted:
        mark.admitted = False
        signals.release()


def finish(request, response):
    now = context.clock()
    mark = getattr(request, "_request_limit", None)
    if mark is None:
        return _not_found(request, response, now)
    release(request)
    status = response.status_code
    signals.record(mark.scope, status, max(0.0, now - mark.started) * 1000, now, served=not mark.refused)
    if status == 429:
        refusals.count(mark.scope, now, by_limiter=mark.refused)
        abuse.strike(mark.scope, mark.key, now)
    smart.evaluate(now)
    return response
