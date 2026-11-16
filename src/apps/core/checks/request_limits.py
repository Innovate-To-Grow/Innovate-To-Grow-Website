"""The request-limit middleware must sit where it works, and every registered scope and check must exist."""

from django.conf import settings
from django.core.checks import Error, Warning, register

REQUEST_LIMIT_MIDDLEWARE = "apps.core.middleware.RequestRateLimitMiddleware"
# The request limiter must come after each of these and before each of the successors (see
# apps/core/middleware/request_limits.py).
REQUEST_LIMIT_PREDECESSORS = (
    "corsheaders.middleware.CorsMiddleware",
    "apps.core.middleware.HealthCheckMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
)
REQUEST_LIMIT_SUCCESSORS = ("django.middleware.csrf.CsrfViewMiddleware",)


def _middleware_problems(enabled: bool) -> list:
    middleware = list(getattr(settings, "MIDDLEWARE", []))
    if REQUEST_LIMIT_MIDDLEWARE not in middleware:
        if not enabled:
            return []
        return [
            Warning(
                "REQUEST_RATE_LIMITS_ENABLED is on but the request limiter is not in MIDDLEWARE.",
                hint=f"Add {REQUEST_LIMIT_MIDDLEWARE!r} after AuthenticationMiddleware.",
                id="core.W001",
            )
        ]
    position = middleware.index(REQUEST_LIMIT_MIDDLEWARE)
    late = [name for name in REQUEST_LIMIT_PREDECESSORS if name in middleware and middleware.index(name) > position]
    early = [name for name in REQUEST_LIMIT_SUCCESSORS if name in middleware and middleware.index(name) < position]
    problems = []
    if late:
        problems.append(
            Error(
                f"The request limiter must come after {', '.join(late)} in MIDDLEWARE.",
                hint="Before CORS its 429 has no CORS headers, before the health checks it would limit the ALB "
                "probes, and before sessions it cannot see the admin user.",
                id="core.E008",
            )
        )
    if early:
        problems.append(
            Error(
                f"The request limiter must come before {', '.join(early)} in MIDDLEWARE.",
                hint="After CSRF a request refused for its CSRF token is never counted, so such a flood is unlimited.",
                id="core.E012",
            )
        )
    return problems


def _registration_problems() -> list:
    from ..services.request_limits.classification.priority import registered_checks
    from ..services.request_limits.classification.scopes import registered

    known = {name for name, spec in settings.REQUEST_RATE_LIMITS["scopes"].items() if spec.get("identity") != "view"}
    scopes, _exemptions = registered()
    unknown = sorted(
        target
        for target, value in scopes.items()
        for scope in (value.values() if isinstance(value, dict) else [value])
        if scope not in known
    )
    problems = []
    if unknown:
        problems.append(
            Error(
                f"register_scope names a scope REQUEST_RATE_LIMITS does not define, for: {', '.join(unknown)}.",
                id="core.E009",
            )
        )
    unchecked = sorted(scope for scope in registered_checks() if scope not in known)
    if unchecked:
        problems.append(
            Error(
                f"register_priority_check names a scope REQUEST_RATE_LIMITS does not define: {', '.join(unchecked)}.",
                id="core.E011",
            )
        )
    return problems


@register()
def check_request_limits(app_configs=None, **kwargs):
    enabled = getattr(settings, "REQUEST_RATE_LIMITS_ENABLED", None)
    if not isinstance(enabled, bool):
        return [Error("REQUEST_RATE_LIMITS_ENABLED must be True or False.", id="core.E010")]
    problems = _middleware_problems(enabled) + _registration_problems()
    exposed = {str(name).lower() for name in getattr(settings, "CORS_EXPOSE_HEADERS", ())}
    if enabled and "retry-after" not in exposed:
        problems.append(
            Warning(
                "CORS_EXPOSE_HEADERS does not include Retry-After.",
                hint="The SPA calls the API cross-origin and cannot read when to retry after a 429.",
                id="core.W002",
            )
        )
    return problems
