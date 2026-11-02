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

# Application service credentials must never fall back to database plaintext.
AWS_CREDENTIALS_REQUIRE_SECRETS_MANAGER = True
# Private keys (credential store) live only in Secrets Manager; the core system check refuses any other backend.
CREDENTIAL_STORE_BACKEND = "secretsmanager"
CREDENTIAL_STORE_REQUIRE_SECRETS_MANAGER = True
# Other Graph configurations require recent, complete evidence of the mailbox restriction and original approval.
GRAPH_REQUIRE_ACCESS_EVIDENCE = True
# The operator accepted OIT's provisioned I2G permissions on 2026-11-02 without waiting for an InfoSec exception or
# complete Exchange isolation validation. This policy does not claim either exists. Identifiers are public app
# metadata; the certificate and its private key remain in the existing admin/credential store.
GRAPH_OIT_PROVISIONED_ACTIVATION = {
    "config_id": "648a5f99-3abc-484d-9ecd-48608dd47832",
    "tenant_id": "f4dfe9a3-ca78-4998-b7a7-e6d0692eace6",
    "client_id": "f50cd7bc-ab45-4698-ab42-ae737a4c8adc",
    "mailbox": "i2g@ucmerced.edu",
    "accepted_roles": ("Mail.Send", "Mail.ReadWrite"),
    "accepted_on": "2026-11-02",
}
