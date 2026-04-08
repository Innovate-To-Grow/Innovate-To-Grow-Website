"""
Development settings.

Usage: ``--settings=core.settings.dev`` (or DJANGO_SETTINGS_MODULE).
Inherits everything from base.py and overrides only what differs locally.
"""

import os

from .base import *  # noqa: F403

# ---------------------------------------------------------------------------
# Core overrides
# ---------------------------------------------------------------------------
SECRET_KEY = "django-insecure-p+tt4i0o$9t!o1707ibkya=&-vlid7@88cz=gcc$*7h$$l1*ai"
DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]
extra = os.environ.get("EXTRA_ALLOWED_HOSTS", "")
if extra:
    ALLOWED_HOSTS += [h.strip() for h in extra.split(",") if h.strip()]

# Plain-text passwords are acceptable for local dev/test convenience
REQUIRE_ENCRYPTED_PASSWORDS = False

# Print emails to console instead of sending
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# ---------------------------------------------------------------------------
# Frontend integration
# ---------------------------------------------------------------------------
# CMS live-preview opens tabs on this origin (Vite dev server default)
if not FRONTEND_URL:  # noqa: F405
    FRONTEND_URL = "http://localhost:5173"
if not BACKEND_URL:  # noqa: F405
    BACKEND_URL = "http://localhost:8000"

CSRF_TRUSTED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

# Include frontend public assets so admin can serve preview styles locally
STATICFILES_DIRS = [
    BASE_DIR / "core" / "static",  # noqa: F405
    BASE_DIR.parent / "pages" / "public" / "static",  # noqa: F405
]

# ---------------------------------------------------------------------------
# Database (SQLite for zero-setup local development)
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
    }
}

# ---------------------------------------------------------------------------
# Caching (in-memory; no external dependencies needed)
# ---------------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "innovate-to-grow-dev",
    }
}
