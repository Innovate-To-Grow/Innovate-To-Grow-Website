"""Promotion to a P0 scope needs proof that a person started the request.

A code request is P0 (never shed for load) only when it is user-initiated: it comes from a signed-in person (a
verified member token or the admin session) or it carries what the normal UI flow sends (a valid anti-abuse proof).
An app says what that proof is with ``register_priority_check(scope, check)`` from ``AppConfig.ready()``;
``check(request)`` must be cheap, read nothing it would change and return a truthy value only for a valid proof:
preferably the proof's own id (a string), so that one solved proof promotes at most ``abuse.proof_promotions``
requests within ``abuse.proof_memory_seconds`` (a retry or two) and a replayed proof is not promoted after that.
A request of such a scope that has neither is **not promoted**: it is counted in ``fallback.unproven`` (P2, per
source and everyone together) instead, so scripted floods without a proof never take P0's reserved capacity. Being promoted is not an
exemption either: the scope's own limits, the per-view limits and abuse escalation still apply.
"""

import logging
from collections.abc import Callable

from django.utils.module_loading import import_string

from . import identity
from .runtime import context, store
from .runtime.context import section

logger = logging.getLogger(__name__)

_CHECKS: dict[str, Callable | str] = {}


def register_priority_check(scope: str, check: Callable | str) -> None:
    """Promote ``scope``'s anonymous requests only when ``check(request)`` (a callable or its dotted path) is true."""
    _CHECKS[scope] = check


def registered_checks() -> dict:
    return dict(_CHECKS)


def _proof(check, request):
    """The check's answer: a proof id (str), True for a proof without one, or False."""
    try:
        result = (import_string(check) if isinstance(check, str) else check)(request)
    except Exception:
        logger.warning("request_limits.priority_check_failed", exc_info=True)
        return False
    return result if isinstance(result, str) and result else bool(result)


def _fresh(scope: str, proof) -> bool:
    """Whether ``proof`` may still promote a request (counting this one)."""
    if proof is True:
        return True
    abuse = section("abuse")
    uses = store.hit(f"proof|{scope}|{proof}", abuse["proof_memory_seconds"], context.clock())
    return uses <= abuse["proof_promotions"]


def promoted_scope(request, scope: str) -> str:
    """``scope`` when the request may have it, else the unproven scope."""
    check = _CHECKS.get(scope)
    if check is None or identity.resolve(request).person is not None:
        return scope
    proof = _proof(check, request)
    if proof and _fresh(scope, proof):
        return scope
    return section("fallback")["unproven"]
