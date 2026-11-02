"""Fast settings for isolated unit tests, selected explicitly by CI test jobs.

Browser E2E and production checks use their separate settings modules. Keep
the default hashers available so existing password fixtures still verify.
"""

from django.conf import global_settings

from .test import *  # noqa: F403

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
    *global_settings.PASSWORD_HASHERS,
]
