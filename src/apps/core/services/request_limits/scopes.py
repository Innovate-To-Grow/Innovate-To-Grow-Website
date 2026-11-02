"""Which scope a request belongs to, so that no route is ever unlimited by accident.

In order, a route is:

1. **exempt** when it is a CORS preflight (OPTIONS with ``Access-Control-Request-Method``; a bare OPTIONS runs the
   view, so it is limited like any other request), the view says so (``rate_limit_exempt = "reason"``), an app
   registered it with ``register_exemption`` or ``REQUEST_RATE_LIMITS["exempt"]`` lists it;
2. in the scope ``REQUEST_RATE_LIMITS["routes"]`` gives it (the deployment's table, so a
   ``REQUEST_RATE_LIMITS_OVERRIDES`` entry can move any route, its own views' included);
3. in the scope its view names (``rate_limit_scope = "scope"`` or ``{"GET": "scope", "*": "scope"}``);
4. in the scope an app registered for it from ``AppConfig.ready()`` (``register_scope``; for third-party views);
5. else in a **fallback** scope: ``cli`` under the CLI prefix, ``staff-admin`` under the admin prefix, otherwise
   ``public-read`` / ``member-read`` for GET, HEAD and a bare OPTIONS and ``public-write`` / ``member-write`` for
   the rest.

A scope with a priority check (``priority.register_priority_check``) is then kept only for a request a person
started; any other is counted in the unproven scope (``fallback.unproven``).

Registrations and settings are keyed by the route's ``view_name`` (``"namespace:name"``) or the view's dotted path.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from . import identity, priority
from .runtime.context import section

SAFE_METHODS = frozenset({"GET", "HEAD"})
PREFLIGHT = "CORS preflight: answered without running the view."

_REGISTERED: dict[str, object] = {}
_EXEMPTIONS: dict[str, str] = {}


@dataclass(frozen=True)
class Classification:
    scope: str | None
    exempt: str | None = None
    # "preflight", "exempt", "route", "view", "registered", "unproven" or "fallback".
    source: str = "fallback"


def register_scope(target: str, scope) -> None:
    """Put the route or view ``target`` (a view_name or dotted view path) in ``scope`` (or a method map)."""
    _REGISTERED[target] = scope


def register_exemption(target: str, reason: str) -> None:
    """Never limit ``target``; ``reason`` says why (shown in the coverage test and the admin)."""
    if not str(reason or "").strip():
        raise ValueError("An exemption needs a reason.")
    _EXEMPTIONS[target] = reason


def registered() -> tuple[dict, dict]:
    """The scopes and exemptions apps registered (copies)."""
    return dict(_REGISTERED), dict(_EXEMPTIONS)


def _view_objects(view_func):
    owners = (getattr(view_func, "view_class", None), getattr(view_func, "cls", None))
    return (view_func, *(owner for owner in owners if owner is not None))


def view_path(view_func) -> str:
    owner = getattr(view_func, "view_class", None) or getattr(view_func, "cls", None) or view_func
    return f"{getattr(owner, '__module__', '')}.{getattr(owner, '__qualname__', type(owner).__qualname__)}"


def _attribute(view_func, name: str):
    for owner in _view_objects(view_func):
        value = getattr(owner, name, None)
        if value is not None:
            return value
    return None


def pick(value, method: str) -> str | None:
    """The scope for ``method`` from a scope or a method map."""
    if isinstance(value, Mapping):
        return value.get(method) or value.get("*")
    return value or None


def _exemption(view_func, keys) -> str | None:
    reason = _attribute(view_func, "rate_limit_exempt")
    if reason:
        return str(reason)
    exempt = section("exempt")
    for key in keys:
        if key in _EXEMPTIONS:
            return _EXEMPTIONS[key]
        if key in exempt:
            return exempt[key]
    return None


def classify_route(view_func, view_name: str | None, method: str) -> Classification | None:
    """The explicit classification of a route for ``method``, or None when the fallback decides."""
    keys = tuple(key for key in (view_name, view_path(view_func)) if key)
    reason = _exemption(view_func, keys)
    if reason:
        return Classification(None, reason, "exempt")
    routes = section("routes")
    for key in keys:
        if key in routes and (scope := pick(routes[key], method)):
            return Classification(scope, None, "route")
    scope = pick(_attribute(view_func, "rate_limit_scope"), method)
    if scope:
        return Classification(scope, None, "view")
    for key in keys:
        if key in _REGISTERED and (scope := pick(_REGISTERED[key], method)):
            return Classification(scope, None, "registered")
    return None


def fallback(path: str, method: str, signed_in: bool) -> str:
    rules = section("fallback")
    if path.startswith(rules["cli_prefix"]):
        return rules["cli"]
    if path.startswith(rules["admin_prefix"]):
        return rules["admin"]
    if method in SAFE_METHODS or method == "OPTIONS":
        return rules["member_read"] if signed_in else rules["public_read"]
    return rules["member_write"] if signed_in else rules["public_write"]


def is_preflight(request) -> bool:
    """A CORS preflight (``CorsMiddleware`` answers it without running the view)."""
    return request.method == "OPTIONS" and "HTTP_ACCESS_CONTROL_REQUEST_METHOD" in request.META


def classify(request, view_func) -> Classification:
    """The scope (or exemption) of a resolved request."""
    method = request.method or "GET"
    if is_preflight(request):
        return Classification(None, PREFLIGHT, "preflight")
    match = getattr(request, "resolver_match", None)
    found = classify_route(view_func, match.view_name if match else None, method)
    if found is not None:
        if found.scope is not None:
            scope = priority.promoted_scope(request, found.scope)
            if scope != found.scope:
                return Classification(scope, None, "unproven")
        return found
    signed_in = identity.resolve(request).person is not None
    return Classification(fallback(request.path_info, method, signed_in), None, "fallback")
