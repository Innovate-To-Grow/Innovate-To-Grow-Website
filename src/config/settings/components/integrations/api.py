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
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    # Throttle *rates* only -- classes are set per-view, not globally.
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/minute",
        "login": "10/minute",
        "email_code_request": "30/minute",
        "email_code_verify": "60/minute",
        # Per-authenticated-user cap on SMS verification sends. Each send spends
        # real AWS SNS money to an attacker-supplied destination, and the
        # service-level cap is keyed per destination number (bypassable by
        # rotating numbers), so this per-actor limit bounds toll-fraud / pumping.
        "phone_code_request": "5/minute",
        # Per-IP cap on the PUBLIC passwordless phone-auth SMS request endpoint.
        # phone_code_request above is a UserRateThrottle (no-op for anonymous
        # callers), so this anon scope is what actually bounds toll-fraud / SMS
        # pumping on the unauthenticated signup/login endpoint.
        "phone_auth_code_request": "5/minute",
        # Per-authenticated-user cap on email verification-code sends (the shared
        # email_code_request throttle is anon-only and a no-op once authenticated,
        # so it cannot stop bombing an attacker-supplied address).
        "email_code_user_request": "5/minute",
        "past_project_share": "10/minute",
        "past_project_ai_search": "10/minute",
        "contact_email_create": "5/hour",
        "ses_events": "600/minute",
        "cli_oauth": "30/minute",
        "cli_read": "120/minute",
        "cli_write": "60/minute",
        "public_assistant": "20/minute",
        # Proof-of-work challenge issuance. Bound independently of send
        # throttles so solvers cannot mint unlimited challenges.
        "send_verification_challenge": "30/minute",
        "send_verification_status": "60/minute",
    },
}

# ---------------------------------------------------------------------------
# Self-hosted send verification (ALTCHA PoW v2 + destination quotas)
# ---------------------------------------------------------------------------
# Mode: observe (proofs optional) | enforce (required) | pause (fail closed).
# None means inherit the active database configuration, then service defaults.
# Only explicit environment/local/test settings override admin changes. HMAC
# secrets for production normally live in SendVerificationConfig (Django admin).
SEND_VERIFICATION_MODE = None
SEND_VERIFICATION_HMAC_SECRET = None
SEND_VERIFICATION_HMAC_KEY_SECRET = None
SEND_VERIFICATION_HMAC_SECRET_PREVIOUS = None
SEND_VERIFICATION_HMAC_KEY_SECRET_PREVIOUS = None
SEND_VERIFICATION_ALGORITHM = None
SEND_VERIFICATION_COST = None
SEND_VERIFICATION_TTL_SECONDS = None
SEND_VERIFICATION_MAX_PAYLOAD_BYTES = None
SEND_VERIFICATION_DESTINATION_HOURLY_LIMIT = None
SEND_VERIFICATION_DESTINATION_COOLDOWN_SECONDS = None
# An uncalibrated effective SMS cap fails closed in enforce mode.
SEND_VERIFICATION_SMS_DAILY_LIMIT = None
SEND_VERIFICATION_IDEMPOTENCY_TTL_SECONDS = None
SEND_VERIFICATION_RETENTION_DAYS = None
SEND_VERIFICATION_CHALLENGE_CACHE_WINDOW_SECONDS = None
SEND_VERIFICATION_CHALLENGE_CACHE_LIMIT = None

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
    "ALGORITHM": "HS256",
    "AUDIENCE": "i2g-api",
    "ISSUER": "i2g-backend",
    "JTI_CLAIM": "jti",
}
