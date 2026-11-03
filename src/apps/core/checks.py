"""System checks for settings that must hold before the site starts.

Every management command runs them, including the startup commands in ``entrypoint.sh`` and the background worker,
so a production task whose key store is not Secrets Manager stops before it serves a request.
"""

from django.conf import settings
from django.core.checks import Error, Tags, Warning, register

from .services.credential_store import BACKENDS, SECRETS_MANAGER, valid_secret_id, valid_staged_label
from .utils.security import is_graph_permission

_POSITIVE_NUMBER_SETTINGS = (
    "CREDENTIAL_STORE_CONNECT_TIMEOUT_SECONDS",
    "CREDENTIAL_STORE_READ_TIMEOUT_SECONDS",
    "CREDENTIAL_STORE_TOTAL_MAX_ATTEMPTS",
    "CREDENTIAL_STORE_MAX_PAYLOAD_BYTES",
    "GRAPH_CERTIFICATE_MIN_RSA_KEY_BITS",
    "GRAPH_CERTIFICATE_MAX_INPUT_BYTES",
    "GRAPH_CERTIFICATE_CHECK_TIMEOUT_SECONDS",
    "GRAPH_CERTIFICATE_EXPIRY_WARNING_DAYS",
    "GRAPH_CERTIFICATE_EXPIRY_CRITICAL_DAYS",
    "GRAPH_ACCESS_CHECK_TIMEOUT_SECONDS",
    "GRAPH_ACCESS_CHECK_MIME_MAX_BYTES",
    "GRAPH_ACCESS_EVIDENCE_MAX_AGE_DAYS",
    "GRAPH_REQUEST_TIMEOUT_SECONDS",
    "GRAPH_MAX_RESPONSE_BYTES",
    "GRAPH_INBOX_LIST_MAX_BYTES",
    "GRAPH_INBOX_MESSAGE_MAX_BYTES",
    "GRAPH_INBOX_MAX_LIST_LIMIT",
    "GRAPH_MAX_RETRY_AFTER_SECONDS",
    "GRAPH_TOKEN_EXPIRY_MARGIN_SECONDS",
    "GRAPH_TOKEN_MAX_LIFETIME_SECONDS",
    "GRAPH_CLIENT_ASSERTION_LIFETIME_SECONDS",
    "GRAPH_ACCESS_CHECK_MAX_ROLES",
)


def _backend_errors() -> list[Error]:
    errors = []
    backend = getattr(settings, "CREDENTIAL_STORE_BACKEND", "")
    if backend not in BACKENDS:
        errors.append(Error(f"CREDENTIAL_STORE_BACKEND must be one of: {', '.join(BACKENDS)}.", id="core.E001"))
    if getattr(settings, "CREDENTIAL_STORE_REQUIRE_SECRETS_MANAGER", False) and backend != SECRETS_MANAGER:
        errors.append(
            Error(
                f"This environment requires CREDENTIAL_STORE_BACKEND = {SECRETS_MANAGER!r}.",
                hint="Private keys may live only in AWS Secrets Manager here; the local file and memory stores "
                "are for development and tests.",
                id="core.E002",
            )
        )
    return errors


def _secret_errors() -> list[Error]:
    errors = []
    secrets = getattr(settings, "CREDENTIAL_STORE_SECRETS", None)
    if isinstance(secrets, dict):
        invalid = sorted(str(name) for name, secret_id in secrets.items() if not valid_secret_id(secret_id))
    else:
        invalid = ["(the setting is not a dict)"]
    if invalid:
        errors.append(
            Error(
                f"CREDENTIAL_STORE_SECRETS has an invalid secret name for: {', '.join(invalid)}.",
                hint="Use a Secrets Manager secret name outside the itg/backend/aws-credentials/ namespace.",
                id="core.E003",
            )
        )
    if not valid_staged_label(getattr(settings, "CREDENTIAL_STORE_STAGED_LABEL", None)):
        errors.append(
            Error("CREDENTIAL_STORE_STAGED_LABEL must be a staging label not starting with AWS.", id="core.E004")
        )
    for name in _POSITIVE_NUMBER_SETTINGS:
        value = getattr(settings, name, None)
        if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
            errors.append(Error(f"{name} must be a positive number.", id="core.E005"))
    return errors


@register(Tags.security)
def check_credential_store(app_configs=None, **kwargs):
    return _backend_errors() + _secret_errors()


def _graph_errors() -> list[Error]:
    errors = []
    roles = getattr(settings, "GRAPH_APPROVED_APPLICATION_ROLES", None)
    if not isinstance(roles, list | tuple) or not roles or not all(is_graph_permission(role) for role in roles):
        errors.append(
            Error(
                "GRAPH_APPROVED_APPLICATION_ROLES must be a non-empty list of Graph permission names.",
                hint='For example ("Mail.Send", "Mail.ReadWrite", "Mail.Read"): the application permissions OIT granted.',
                id="core.E006",
            )
        )
    if not isinstance(getattr(settings, "GRAPH_REQUIRE_ACCESS_EVIDENCE", None), bool):
        errors.append(Error("GRAPH_REQUIRE_ACCESS_EVIDENCE must be True or False.", id="core.E007"))
    return errors


@register(Tags.security)
def check_microsoft_graph(app_configs=None, **kwargs):
    return _graph_errors()


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
    from .services.request_limits.priority import registered_checks
    from .services.request_limits.scopes import registered

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
