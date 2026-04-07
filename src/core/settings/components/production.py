"""
Production-only settings.

Imported by ``prod.py`` on top of ``base.py``.  All secrets and host names
come from environment variables -- nothing is hard-coded for production use.
"""

import os

from django.core.exceptions import ImproperlyConfigured

from .framework.environment import BASE_DIR


def _get_required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ImproperlyConfigured(f"{name} must be set in production.")
    return value


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
SECRET_KEY = _get_required_env("DJANGO_SECRET_KEY")
DEBUG = False
ALLOWED_HOSTS = [host.strip() for host in _get_required_env("DJANGO_ALLOWED_HOSTS").split(",") if host.strip()]

# ---------------------------------------------------------------------------
# Database (PostgreSQL with SSL required)
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": os.environ.get("DB_ENGINE", "django.db.backends.postgresql"),
        "NAME": _get_required_env("DB_NAME"),
        "USER": _get_required_env("DB_USER"),
        "PASSWORD": _get_required_env("DB_PASSWORD"),
        "HOST": _get_required_env("DB_HOST"),
        "PORT": os.environ.get("DB_PORT", "5432"),
        "CONN_MAX_AGE": 60,  # Persistent connections (seconds)
        "OPTIONS": {"sslmode": "require"},
    }
}

# ---------------------------------------------------------------------------
# Security hardening
# ---------------------------------------------------------------------------
REQUIRE_ENCRYPTED_PASSWORDS = True
RSA_KEY_PASSPHRASE = _get_required_env("RSA_KEY_PASSPHRASE")

# HTTP security headers
SECURE_SERVER_HEADER = None  # Do not expose server software
SECURE_CONTENT_TYPE_NOSNIFF = True  # Prevent MIME-type sniffing
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_SSL_REDIRECT = False  # Handled by reverse proxy
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Cookie security
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"

# CORS / CSRF trusted origins (comma-separated env vars)
CSRF_TRUSTED_ORIGINS = (
    os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if os.environ.get("CSRF_TRUSTED_ORIGINS") else []
)
CORS_ALLOWED_ORIGINS = (
    os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",") if os.environ.get("CORS_ALLOWED_ORIGINS") else []
)
CORS_ALLOW_CREDENTIALS = True

# ---------------------------------------------------------------------------
# AWS S3 storage (static files and media uploads)
# ---------------------------------------------------------------------------
AWS_STORAGE_BUCKET_NAME = _get_required_env("AWS_STORAGE_BUCKET_NAME")
AWS_S3_REGION_NAME = os.environ.get("AWS_S3_REGION_NAME", "us-west-2")
AWS_S3_CUSTOM_DOMAIN = os.environ.get("AWS_S3_CUSTOM_DOMAIN", f"{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com")
AWS_DEFAULT_ACL = None  # Inherit bucket policy
AWS_S3_FILE_OVERWRITE = False  # Never silently overwrite uploads
AWS_QUERYSTRING_AUTH = False  # Public URLs (no signed query strings)
AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "max-age=86400"}  # 1-day browser cache

STATIC_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/media/"

STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        "OPTIONS": {
            "bucket_name": AWS_STORAGE_BUCKET_NAME,
            "region_name": AWS_S3_REGION_NAME,
            "location": "media",
            "file_overwrite": False,
            "querystring_auth": False,
            "default_acl": None,
            "object_parameters": AWS_S3_OBJECT_PARAMETERS,
        },
    },
    "staticfiles": {
        "BACKEND": "storages.backends.s3boto3.S3StaticStorage",
        "OPTIONS": {
            "bucket_name": AWS_STORAGE_BUCKET_NAME,
            "region_name": AWS_S3_REGION_NAME,
            "location": "static",
            "querystring_auth": False,
            "default_acl": None,
            "object_parameters": AWS_S3_OBJECT_PARAMETERS,
        },
    },
}

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_PROVIDER = os.environ.get("EMAIL_PROVIDER", "gmail")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "i2g@g.ucmerced.edu")

# ---------------------------------------------------------------------------
# Logging (structured console output for container environments)
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Caching (Redis preferred; falls back to file-based cache)
# ---------------------------------------------------------------------------
REDIS_URL = os.environ.get("REDIS_URL", "").strip()
CACHES = (
    {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
            "KEY_PREFIX": "i2g",
            "TIMEOUT": 300,  # 5-minute default TTL
        }
    }
    if REDIS_URL
    else {
        "default": {
            "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
            "LOCATION": os.environ.get("DJANGO_CACHE_DIR", "/tmp/innovate-to-grow-cache"),
            "KEY_PREFIX": "i2g",
            "TIMEOUT": 300,
        }
    }
)
