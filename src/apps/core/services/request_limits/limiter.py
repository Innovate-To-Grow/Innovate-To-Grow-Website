"""The request path: ``admit`` before the view runs, ``finish`` after it answered.

``admit`` classifies the request, then refuses it (429 with Retry-After) when its caller (or, without a verified
identity, its source) is blocked for the scope (abuse escalation), over the per-caller limit, over the per-source
flood ceiling, over the scope's aggregate cap, or — last, so a refused request never holds a slot — when its tier has
no concurrency slot left. Only a refusal of the caller's own making is an abuse strike (``runtime/abuse.py``): its
own limit or flood ceiling exceeded at full size. ``finish`` frees the slot, records the signals Smart limiting
reads, counts the 429s in the admin's recent refusals, strikes a 429 the view itself answered when the caller has
its own key (not a shared IP), and lets the controller assess a window that just ended. Requests for paths no route
matches are limited afterwards in the ``not-found`` scope.
"""

import math
from dataclasses import dataclass

from django.http import JsonResponse

from . import identity, scopes
from .rules.limits import effective_limits, strike_limits
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


@dataclass(frozen=True)
class Refusal:
    retry: float
    # The bucket the refusal is struck against; None when it is not the caller's doing (the aggregate cap, a lack
    # of slots, a block already running).
    strike: str | None = None


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


def _blocked(scope: str, buckets, now: float) -> Refusal | None:
    waits = [wait for bucket in buckets if (wait := abuse.blocked_for(scope, bucket, now)) is not None]
    return Refusal(max(waits)) if waits else None


def _over_limit(config, key: str | None, source: str | None, now: float) -> Refusal | None:
    """Count the request; the refusal when it is over a limit, else None."""
    processes = live_processes(now)
    limits = effective_limits(config, processes)
    reset = store.window_reset(limits.period, now)
    buckets = ((key, key, "per_identity"), (f"src|{source}" if source else None, source, "source_cap"))
    for bucket, name, field in buckets:
        limit = getattr(limits, field)
        if bucket is None or limit is None:
            continue
        count = store.hit(f"{config.scope}|{bucket}", limits.period, now)
        if count > limit:
            return Refusal(reset, name if count > getattr(strike_limits(config, processes), field) else None)
    if limits.global_cap is not None and store.hit(f"{config.scope}|*", limits.period, now) > limits.global_cap:
        return Refusal(reset)
    return None


def _check(request, config, now: float) -> tuple[str | None, Refusal | None]:
    key = identity.bucket_key(request, config.scope, config.identity)
    source = identity.source_key(request, key) if config.source_cap else None
    return key, _blocked(config.scope, (key, source), now) or _over_limit(config, key, source, now)


def admit(request, view_func):
    """None to let the request through, or the 429 response."""
    now = context.clock()
    found = scopes.classify(request, view_func)
    if found.scope is None:
        return None
    config = registry.configs(now).get(found.scope)
    if config is None or not config.enabled:
        return None
    key, refusal = _check(request, config, now)
    mark = Mark(config.scope, config.tier, key, now)
    request._request_limit = mark
    if refusal is None:
        if signals.admit(config.tier, now):
            mark.admitted = True
            return None
        refusal = Refusal(section("admission")["retry_after_seconds"])
    mark.refused = True
    abuse.strike(config.scope, refusal.strike, now)
    return rejection(refusal.retry)


def _not_found(request, response, now: float):
    if getattr(request, "resolver_match", None) is not None or response.status_code != 404:
        return response
    if scopes.is_preflight(request):
        return response
    scope = section("fallback")["not_found"]
    config = registry.configs(now).get(scope)
    if config is None or not config.enabled:
        return response
    _key, refusal = _check(request, config, now)
    if refusal is None:
        return response
    signals.record(scope, 429, 0.0, now, served=False)
    refusals.count(scope, now, by_limiter=True)
    abuse.strike(scope, refusal.strike, now)
    return rejection(refusal.retry)


def release(request) -> None:
    """Give back the request's slot (once)."""
    mark = getattr(request, "_request_limit", None)
    if mark is not None and mark.admitted:
        mark.admitted = False
        signals.release()


def _own_key(key: str | None) -> bool:
    """A key one caller owns (a person, a CLI token, a destination), not an IP many callers may share."""
    return key is not None and not key.startswith("ip:")


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
        if not mark.refused and _own_key(mark.key):
            abuse.strike(mark.scope, mark.key, now)
    smart.evaluate(now)
    return response
