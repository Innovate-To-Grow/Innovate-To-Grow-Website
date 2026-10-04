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
        "email_code_verify": "60/minute",
        # Per-authenticated-user cap on SMS verification sends. Each send spends
        # real AWS SNS money to an attacker-supplied destination, and the
        # service-level cap is keyed per destination number (bypassable by
        # rotating numbers), so this per-actor limit bounds toll-fraud / pumping.
        "phone_code_request": "5/minute",
        # Per-IP cap on the PUBLIC passwordless phone-auth SMS request endpoint.
        # phone_code_request above is a UserRateThrottle (no-op for anonymous
        # callers). This anon scope is a fallback speed bump, attached only
        # while no SMS daily budget is configured; the bounds on toll-fraud /
        # SMS pumping are the per-number caps and that budget.
        "phone_auth_code_request": "5/minute",
        # Per-authenticated-user cap on email verification-code sends (an anon,
        # per-IP throttle is a no-op once authenticated, so it cannot stop
        # bombing an attacker-supplied address).
        "email_code_user_request": "5/minute",
        "past_project_share": "10/minute",
        "past_project_ai_search": "10/minute",
        "contact_email_create": "5/hour",
        "ses_events": "600/minute",
        "cli_read": "120/minute",
        "cli_write": "60/minute",
        # Per ACTOR (signed visitor value or member), never per IP: see
        # apps.system_intelligence.views.public_assistant.PublicAssistantActorThrottle.
        "public_assistant": "6/minute",
    },
}
# Deliberately absent: per-IP rates for password login, email-link exchange, verification-code request/verify
# and ALTCHA challenge/status. Most users share one campus IP, so such a bucket throttles everyone at once (and
# is bypassable through X-Forwarded-For). Those flows are bounded per token / destination / challenge and, for
# password login, by the identifier-keyed lockout in apps.authn.services.login_guard.

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
