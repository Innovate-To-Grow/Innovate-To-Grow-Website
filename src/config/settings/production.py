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
