"""
Request limits: one middleware (``apps.core.middleware.RequestRateLimitMiddleware``) limits every request the site
answers — DRF and plain views, the Django admin, the CLI API and webhooks — by **scope** (an endpoint group).

- ``scopes.py``: every scope with its priority tier, identity and seeds (each seeds a ``RequestRateLimitPolicy``).
- ``routes.py``: which routes belong to which scope, and the reasoned exemptions.
- ``runtime.py``: the Smart controller and its tier order, admission control, abuse escalation, the counter store.

Smart limiting is on by default for every scope and takes priority over the manual limit (as delivery rates do):
the limit is the scope's baseline × a Smart factor that falls under overload (P3 first, then P2, then P1; never P0)
and recovers when the site is healthy (P1 first). The per-view DRF throttles stay underneath as finer limits.

A deployment changes any value with the ``REQUEST_RATE_LIMITS_OVERRIDES`` environment variable, a JSON object
deep-merged into the defaults (it may add or, with ``null``, remove routes and exemptions)::

    REQUEST_RATE_LIMITS_OVERRIDES='{"scopes": {"public-read": {"global_cap": 20000}}}'

The result is validated at import: a bad value raises ``ImproperlyConfigured`` before the site starts.
``REQUEST_RATE_LIMITS_ENABLED`` (env, default true) turns the middleware off; the test settings turn it off unless
the environment enables it, and dedicated tests switch it on with ``override_settings``.
"""

import os

from .routes import EXEMPT, ROUTES
from .runtime import ABUSE, ADMISSION, CONTROLLER, FALLBACK, STORE, TIERS
from .scopes import SCOPES
from .validation import OVERRIDES_ENV, load_request_limits

__all__ = ["REQUEST_RATE_LIMITS", "REQUEST_RATE_LIMITS_ENABLED"]

DEFAULTS = {
    "scopes": SCOPES,
    "routes": ROUTES,
    "exempt": EXEMPT,
    "tiers": TIERS,
    "controller": CONTROLLER,
    "admission": ADMISSION,
    "abuse": ABUSE,
    "store": STORE,
    "fallback": FALLBACK,
}

REQUEST_RATE_LIMITS = load_request_limits(DEFAULTS, os.environ.get(OVERRIDES_ENV, ""))


def enabled_from_env(default: bool) -> bool:
    """``REQUEST_RATE_LIMITS_ENABLED`` from the environment (1/true/yes/on or 0/false/no/off), else ``default``."""
    value = os.environ.get("REQUEST_RATE_LIMITS_ENABLED", "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


REQUEST_RATE_LIMITS_ENABLED = enabled_from_env(True)
