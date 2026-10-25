"""
Production settings entrypoint.

Inherits everything from config.settings.base, then layers on the overrides
from config.settings.production (security, S3, logging, caching).
"""

# ruff: noqa: I001
from ..base import *  # noqa: F403
from ..production.django import *  # noqa: F403
from ..production.security import *  # noqa: F403
from ..production.storage import *  # noqa: F403
from ..production.verification import *  # noqa: F403
from ..production.cache import *  # noqa: F403

# Append only after ``base`` has assembled the middleware list. Production
# modules use separate namespaces and can silently leave production without a
# CSP header if they try to extend the list themselves.
MIDDLEWARE = [*MIDDLEWARE, "apps.core.middleware.ContentSecurityPolicyMiddleware"]  # noqa: F405

# DRF's throttle ``get_ident()`` reads ``api_settings.NUM_PROXIES``, i.e. ``REST_FRAMEWORK["NUM_PROXIES"]``,
# never the top-level Django setting. Without it every per-IP throttle keys on the whole client-supplied
# ``X-Forwarded-For`` header, so a forged leading entry gets a fresh bucket. Copy rather than mutate: the dict
# is shared with ``base`` (and the local/test entrypoints).
REST_FRAMEWORK = {**REST_FRAMEWORK, "NUM_PROXIES": NUM_PROXIES}  # noqa: F405
