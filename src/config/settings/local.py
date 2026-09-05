"""
Local development settings.

Usage: ``--settings=config.settings.local`` (or DJANGO_SETTINGS_MODULE).
Inherits everything from base.py and overrides only what differs locally.
"""

import os
import sys

from .base import *  # noqa: F403

# ---------------------------------------------------------------------------
# Core overrides
# ---------------------------------------------------------------------------
SECRET_KEY = "django-insecure-p+tt4i0o$9t!o1707ibkya=&-vlid7@88cz=gcc$*7h$$l1*ai"
DEBUG = True

# This is a Django Host-header allowlist entry for the local dev server, not a
# socket bind address.
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]  # nosec B104
extra = os.environ.get("EXTRA_ALLOWED_HOSTS", "")
if extra:
    ALLOWED_HOSTS += [h.strip() for h in extra.split(",") if h.strip()]

# Plain-text passwords are acceptable for local dev/test convenience
REQUIRE_ENCRYPTED_PASSWORDS = False

# Admin confirmation — require typed verification for all admin changes
ADMIN_REQUIRE_CONFIRMATION = True

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

# Append frontend public assets so admin can serve preview styles locally. Extend
# the base list rather than replacing it, so the vendor directory stays included.
STATICFILES_DIRS = [
    *STATICFILES_DIRS,  # noqa: F405
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

# Self-hosted send verification: enforce locally so missing proofs fail in dev.
# HMAC values are development-only; production secrets live in Site Settings.
SEND_VERIFICATION_MODE = "enforce"
SEND_VERIFICATION_HMAC_SECRET = "local-send-verification-hmac-secret"
SEND_VERIFICATION_HMAC_KEY_SECRET = "local-send-verification-hmac-key-secret"
SEND_VERIFICATION_COST = 500
SEND_VERIFICATION_SMS_DAILY_LIMIT = 1000
if "test" in sys.argv:
    SEND_VERIFICATION_TEST_AUTOSOLVE = True
    SEND_VERIFICATION_COST = 10
    SEND_VERIFICATION_DESTINATION_COOLDOWN_SECONDS = 0
    SEND_VERIFICATION_CHALLENGE_CACHE_LIMIT = 10_000
    REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {  # noqa: F405
        **REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],  # noqa: F405
        "send_verification_challenge": "10000/minute",
        "send_verification_status": "10000/minute",
    }
