"""
Django production settings for core project.

This file contains settings specific to the production environment.
"""

import os

from .base import *

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "change-me-in-production")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",")

# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": os.environ.get("DB_ENGINE", "django.db.backends.postgresql"),
        "NAME": os.environ.get("DB_NAME", "innovate_to_grow"),
        "USER": os.environ.get("DB_USER", "user"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "password"),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
        "OPTIONS": {
            "sslmode": "require",
        },
    }
}

# Production-specific settings

# Security settings
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
# SSL termination is handled by ALB, so disable SSL redirect in Django
SECURE_SSL_REDIRECT = False
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = "DENY"

# CSRF trusted origins (set to your domain, e.g. https://api.innovatetogrow.com)
CSRF_TRUSTED_ORIGINS = (
    os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if os.environ.get("CSRF_TRUSTED_ORIGINS") else []
)

# CORS for frontend API access from a separate origin (e.g. Amplify domain)
CORS_ALLOWED_ORIGINS = (
    os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",") if os.environ.get("CORS_ALLOWED_ORIGINS") else []
)
CORS_ALLOW_CREDENTIALS = True

# AWS S3 Storage Configuration
# Required env vars: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
# (or use IAM role-based auth on EC2/ECS/Lambda)
AWS_STORAGE_BUCKET_NAME = os.environ.get("AWS_STORAGE_BUCKET_NAME", "itg-static-assets")
AWS_S3_REGION_NAME = os.environ.get("AWS_S3_REGION_NAME", "us-west-2")
AWS_S3_CUSTOM_DOMAIN = os.environ.get(
    "AWS_S3_CUSTOM_DOMAIN",
    f"{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com",
)
AWS_DEFAULT_ACL = None
AWS_S3_FILE_OVERWRITE = False  # Don't overwrite files with the same name
AWS_QUERYSTRING_AUTH = False  # Serve media via public URLs (no signed querystring)
AWS_S3_OBJECT_PARAMETERS = {
    "CacheControl": "max-age=86400",
}

# Static files on S3 under /static/ prefix
STATIC_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Media files on S3 under /media/ prefix
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

# Email settings
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", 587))
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "i2g@g.ucmerced.edu")

# Logging configuration for production
# Uncomment and create logs directory when ready for production
# import os
# os.makedirs(BASE_DIR / 'logs', exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
    },
    "handlers": {
        # 'file': {
        #     'level': 'INFO',
        #     'class': 'logging.FileHandler',
        #     'filename': BASE_DIR / 'logs' / 'django.log',
        #     'formatter': 'verbose',
        # },
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],  # Remove 'file' until logs directory is created
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],  # Remove 'file' until logs directory is created
            "level": "INFO",
            "propagate": False,
        },
    },
}

# Cache settings with Redis (fallback to in-memory cache if REDIS_URL is not provided)
REDIS_URL = os.environ.get("REDIS_URL", "").strip()
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
            },
            "KEY_PREFIX": "i2g",
            "TIMEOUT": 300,  # Default 5-minute timeout
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "innovate-to-grow-prod-fallback",
            "KEY_PREFIX": "i2g",
            "TIMEOUT": 300,
        }
    }
