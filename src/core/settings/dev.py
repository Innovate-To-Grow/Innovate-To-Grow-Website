"""
Django development settings for core project.

This file contains settings specific to the development environment.
"""

import os

from .base import *

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "django-insecure-p+tt4i0o$9t!o1707ibkya=&-vlid7@88cz=gcc$*7h$$l1*ai"

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]
extra = os.environ.get("EXTRA_ALLOWED_HOSTS", "")
if extra:
    ALLOWED_HOSTS += [h.strip() for h in extra.split(",") if h.strip()]

# Password encryption not required in development (allows plain passwords for testing)
REQUIRE_ENCRYPTED_PASSWORDS = False

# Frontend URL for CMS live preview (admin opens preview tabs on this origin)
if not FRONTEND_URL:
    FRONTEND_URL = "http://localhost:5173"

CSRF_TRUSTED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

# Static files - include frontend static files for preview and custom admin styles
STATICFILES_DIRS = [
    BASE_DIR / "core" / "static",
    BASE_DIR.parent / "pages" / "public" / "static",
]

# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Development-specific settings

# Cache configuration - use in-memory cache for development
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "innovate-to-grow-dev",
    }
}

# Example: Email backend for development
# EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Example: Logging configuration for development
# LOGGING = {
#     'version': 1,
#     'disable_existing_loggers': False,
#     'handlers': {
#         'console': {
#             'class': 'logging.StreamHandler',
#         },
#     },
#     'loggers': {
#         'django': {
#             'handlers': ['console'],
#             'level': 'INFO',
#         },
#     },
# }
