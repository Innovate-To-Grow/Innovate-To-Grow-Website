"""
CI pipeline settings.

Used by GitHub Actions (or similar) for automated test / check runs.
Mirrors production constraints (DEBUG=False, PostgreSQL) but with
throwaway credentials.
"""

import os

from ..base import *  # noqa: F403
from ..base.integrations.request_limits import enabled_from_env

SECRET_KEY = "ci-secret-key"
DEBUG = False
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
CORS_ALLOWED_ORIGINS = ["http://127.0.0.1:4173", "http://localhost:4173"]
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS

# ---------------------------------------------------------------------------
# Database (PostgreSQL service container spun up by CI)
# ---------------------------------------------------------------------------
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

# Unit tests keep confirmation disabled by default. Browser E2E enables it with
# an environment override so the live admin flow matches production behavior.
ADMIN_REQUIRE_CONFIRMATION = os.environ.get("ADMIN_REQUIRE_CONFIRMATION", "false").lower() in {
    "1",
    "true",
    "yes",
}

# Enforce send verification in CI. Existing send tests attach a solved proof via
# the test client helper. Dedicated tests cover missing/forged proofs.
# Deterministic fixture keys belong only to this isolated test settings module.
SEND_VERIFICATION_MODE = "enforce"
SEND_VERIFICATION_HMAC_SECRET = "test-send-verification-hmac-secret"  # nosec B105
SEND_VERIFICATION_HMAC_KEY_SECRET = "test-send-verification-hmac-key-secret"  # nosec B105
SEND_VERIFICATION_COST = 10
SEND_VERIFICATION_DESTINATION_COOLDOWN_SECONDS = 0
SEND_VERIFICATION_SMS_DAILY_LIMIT = 1000
SEND_VERIFICATION_TEST_AUTOSOLVE = True

# Private keys stay in process memory: tests never touch Secrets Manager or the local key directory.
CREDENTIAL_STORE_BACKEND = "memory"

# The request limiter stays off for the test suites, browser E2E and the container smoke job (every test client is
# one IP and one process); dedicated tests switch it on with override_settings, and REQUEST_RATE_LIMITS_ENABLED=true
# turns it on for a run that should exercise it.
REQUEST_RATE_LIMITS_ENABLED = enabled_from_env(False)
