"""
CI pipeline settings.

Used by GitHub Actions (or similar) for automated test / check runs.
Mirrors production constraints (DEBUG=False, PostgreSQL) but with
throwaway credentials.
"""

import os

from .base import *  # noqa: F403

SECRET_KEY = "ci-secret-key"
DEBUG = False
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

# ---------------------------------------------------------------------------
# Database (PostgreSQL service container spun up by CI)
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": os.environ.get("DB_ENGINE", "django.db.backends.postgresql"),
        "NAME": os.environ.get("DB_NAME", "itg_ci"),
        "USER": os.environ.get("DB_USER", "itg_ci_user"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "itg_ci_pass"),
        "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}
