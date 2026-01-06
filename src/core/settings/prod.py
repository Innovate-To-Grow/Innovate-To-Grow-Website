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
    }
}


# Production-specific settings

# Security settings
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = "DENY"

# Static files settings for production
STATIC_ROOT = BASE_DIR / "staticfiles"
STATIC_URL = "/static/"

# Media files
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Cloud Storage Configuration (S3-compatible)
# -------------------------------------------
# Uncomment and configure for cloud storage (AWS S3, Cloudflare R2, etc.)
#
# STORAGES = {
#     "default": {
#         "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
#         "OPTIONS": {
#             "bucket_name": os.environ.get("AWS_STORAGE_BUCKET_NAME", ""),
#             "access_key": os.environ.get("AWS_ACCESS_KEY_ID", ""),
#             "secret_key": os.environ.get("AWS_SECRET_ACCESS_KEY", ""),
#             "region_name": os.environ.get("AWS_S3_REGION_NAME", "us-east-1"),
#             # For Cloudflare R2:
#             # "endpoint_url": os.environ.get("AWS_S3_ENDPOINT_URL", ""),
#             # Custom domain for CDN:
#             # "custom_domain": os.environ.get("AWS_S3_CUSTOM_DOMAIN", ""),
#         },
#     },
#     "staticfiles": {
#         "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
#     },
# }
# 
# # Update MEDIA_URL for cloud storage
# AWS_S3_CUSTOM_DOMAIN = os.environ.get("AWS_S3_CUSTOM_DOMAIN", "")
# if AWS_S3_CUSTOM_DOMAIN:
#     MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/"

# Email settings
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", 587))
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "noreply@innovatetogrow.com")

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

# Cache settings (example with Redis)
# CACHES = {
#     "default": {
#         "BACKEND": "django_redis.cache.RedisCache",
#         "LOCATION": os.environ.get('REDIS_URL', 'redis://127.0.0.1:6379/1'),
#         "OPTIONS": {
#             "CLIENT_CLASS": "django_redis.client.DefaultClient",
#         }
#     }
# }
