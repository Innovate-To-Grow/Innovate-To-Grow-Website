"""
Production settings entrypoint.

Inherits everything from base.py, then layers on production-specific
overrides from components/production.py (security, S3, logging, caching).
"""

from .base import *  # noqa: F403
from .components.production import *  # noqa: F403
