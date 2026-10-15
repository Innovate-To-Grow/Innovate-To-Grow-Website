"""
Production settings entrypoint.

Inherits everything from base.py, then layers on production-specific
overrides from components/production.py (security, S3, logging, caching).
"""

from .base import *  # noqa: F403
from .components.production import *  # noqa: F403

# Append only after ``base`` has assembled the middleware list. Doing this
# inside the production component uses a separate module namespace and can
# silently leave production without a CSP header.
MIDDLEWARE = [*MIDDLEWARE, "apps.core.middleware.ContentSecurityPolicyMiddleware"]  # noqa: F405

# DRF's throttle ``get_ident()`` reads ``api_settings.NUM_PROXIES``, i.e. ``REST_FRAMEWORK["NUM_PROXIES"]``,
# never the top-level Django setting. Without it every per-IP throttle keys on the whole client-supplied
# ``X-Forwarded-For`` header, so a forged leading entry gets a fresh bucket. Copy rather than mutate: the dict
# is shared with ``base`` (and the local/test entrypoints).
REST_FRAMEWORK = {**REST_FRAMEWORK, "NUM_PROXIES": NUM_PROXIES}  # noqa: F405
