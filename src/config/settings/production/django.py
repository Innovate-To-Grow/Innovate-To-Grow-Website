"""Core Django, database, email, and logging settings for production."""

import os

from .env import _get_bool_env, _get_int_env, _get_required_env

# Core
SECRET_KEY = _get_required_env("DJANGO_SECRET_KEY")
DEBUG = False
ALLOWED_HOSTS = [host.strip() for host in _get_required_env("DJANGO_ALLOWED_HOSTS").split(",") if host.strip()]
BACKEND_URL = _get_required_env("BACKEND_URL")

# Database (PostgreSQL with SSL required)
DATABASES = {
    "default": {
        "ENGINE": os.environ.get("DB_ENGINE", "django.db.backends.postgresql"),
        "NAME": _get_required_env("DB_NAME"),
        "USER": _get_required_env("DB_USER"),
        "PASSWORD": _get_required_env("DB_PASSWORD"),
        "HOST": _get_required_env("DB_HOST"),
        "PORT": os.environ.get("DB_PORT", "5432"),
        "CONN_MAX_AGE": _get_int_env("DB_CONN_MAX_AGE", 0),
        "CONN_HEALTH_CHECKS": _get_bool_env("DB_CONN_HEALTH_CHECKS", True),
        "OPTIONS": {"sslmode": "require"},
    }
}

# Email metadata. Application email services send through AWS SES directly.
EMAIL_BACKEND = "django.core.mail.backends.dummy.EmailBackend"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "i2g@g.ucmerced.edu")

# Logging (structured console output for container environments)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "verbose"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {"django": {"handlers": ["console"], "level": "INFO", "propagate": False}},
}
