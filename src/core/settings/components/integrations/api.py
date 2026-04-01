"""
Django REST Framework and SimpleJWT configuration.

NOTE: Do NOT set DEFAULT_THROTTLE_CLASSES globally here -- doing so applies
throttling to every view (including tests hitting 127.0.0.1) and causes
widespread test failures.  Per-view throttles are applied via throttle_classes.
"""

from datetime import timedelta

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    # Throttle *rates* only -- classes are set per-view, not globally.
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/minute",
        "login": "10/minute",
        "email_code_request": "10/minute",
        "email_code_verify": "20/minute",
        "past_project_share": "10/minute",
    },
}

# ---------------------------------------------------------------------------
# SimpleJWT
# ---------------------------------------------------------------------------
# USER_ID_FIELD must be "id" (the actual DB column on Member, a UUID).
# USER_ID_CLAIM is "member_uuid" so the JWT payload key stays consistent.
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,  # Old refresh tokens are blacklisted on rotation
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",  # DB column (UUID PK)
    "USER_ID_CLAIM": "member_uuid",  # JWT payload claim name
}
