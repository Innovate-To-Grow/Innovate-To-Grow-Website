"""
Django CI settings for core project.

This file contains settings specific to CI validation jobs.
"""

import os

from .base import *

SECRET_KEY = "ci-secret-key"
DEBUG = False
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

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
