"""Production-only settings."""

import os

from .environment import BASE_DIR

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "change-me-in-production")
DEBUG = False
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",")

DATABASES = {
    "default": {
        "ENGINE": os.environ.get("DB_ENGINE", "django.db.backends.postgresql"),
        "NAME": os.environ.get("DB_NAME", "innovate_to_grow"),
        "USER": os.environ.get("DB_USER", "user"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "password"),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
        "CONN_MAX_AGE": 60,
        "OPTIONS": {"sslmode": "require"},
    }
}

REQUIRE_ENCRYPTED_PASSWORDS = True
RSA_KEY_PASSPHRASE = os.environ.get("RSA_KEY_PASSPHRASE")
SECURE_SERVER_HEADER = None
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_HSTS_SECONDS = 31536000
SECURE_SSL_REDIRECT = False
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
CSRF_TRUSTED_ORIGINS = (
    os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if os.environ.get("CSRF_TRUSTED_ORIGINS") else []
)
CORS_ALLOWED_ORIGINS = (
    os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",") if os.environ.get("CORS_ALLOWED_ORIGINS") else []
)
CORS_ALLOW_CREDENTIALS = True

AWS_STORAGE_BUCKET_NAME = os.environ.get("AWS_STORAGE_BUCKET_NAME", "itg-static-assets")
AWS_S3_REGION_NAME = os.environ.get("AWS_S3_REGION_NAME", "us-west-2")
AWS_S3_CUSTOM_DOMAIN = os.environ.get("AWS_S3_CUSTOM_DOMAIN", f"{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com")
AWS_DEFAULT_ACL = None
AWS_S3_FILE_OVERWRITE = False
AWS_QUERYSTRING_AUTH = False
AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "max-age=86400"}
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

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_PROVIDER = os.environ.get("EMAIL_PROVIDER", "gmail")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "i2g@g.ucmerced.edu")

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

REDIS_URL = os.environ.get("REDIS_URL", "").strip()
CACHES = (
    {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
            "KEY_PREFIX": "i2g",
            "TIMEOUT": 300,
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
