"""
Base settings entrypoint.

Assembles all component fragments via wildcard imports so that environment
files (dev.py, prod.py, ci.py) can simply ``from .base import *`` and then
apply their own overrides.

Import order matters: environment first (BASE_DIR), then django (uses
BASE_DIR), then the rest which are order-independent.
"""

from .components.framework.environment import *  # noqa: F403  # BASE_DIR, .env, shared env vars
from .components.framework.django import *  # noqa: F403       # apps, middleware, templates, auth, static
from .components.integrations.api import *  # noqa: F403       # DRF + SimpleJWT
from .components.integrations.admin import *  # noqa: F403     # Unfold admin theme
from .components.integrations.editor import *  # noqa: F403    # CKEditor 5
