"""
Shared Django settings assembled from framework and integration modules.

Environment entrypoints import these settings before applying their overrides.
Import order matters: environment first (BASE_DIR), then django (uses BASE_DIR),
then the rest which are order-independent. The ``I001`` suppression below keeps
this intentional order.
"""

# ruff: noqa: I001
# Install the legacy app-import meta-path finder before any first-party app import.
from .framework import legacy_imports  # noqa: F401
from .framework.environment import *  # noqa: F403  # BASE_DIR, .env, shared env vars
from .framework.django import *  # noqa: F403       # apps, middleware, templates, auth, static
from .framework.cache import *  # noqa: F403        # dev/CI CACHES + the shared throttle alias
from .integrations.admin import *  # noqa: F403     # Unfold admin theme
from .integrations.api import *  # noqa: F403       # DRF + SimpleJWT
from .integrations.editor import *  # noqa: F403    # CKEditor 5
from .integrations.credential_store import *  # noqa: F403  # private-key store backend + secret names
from .integrations.microsoft_graph import *  # noqa: F403  # Graph certificate limits
from .integrations.gmail_api import *  # noqa: F403  # Gmail API request limits, token lifetimes, key entry
from .integrations.delivery_rates import *  # noqa: F403  # per-channel rate seeds, Smart rate controller
from .integrations.request_limits import *  # noqa: F403  # inbound request-limit scopes, tiers, Smart limiting
from .integrations.email_monitoring import *  # noqa: F403  # email telemetry, retention, bounce processing
