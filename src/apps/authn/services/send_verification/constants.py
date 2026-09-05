from __future__ import annotations

MODE_OBSERVE = "observe"
MODE_ENFORCE = "enforce"
MODE_PAUSE = "pause"
ALLOWED_MODES = frozenset({MODE_OBSERVE, MODE_ENFORCE, MODE_PAUSE})

ALGORITHM_PBKDF2_SHA256 = "PBKDF2/SHA-256"
ALLOWED_ALGORITHMS = frozenset({ALGORITHM_PBKDF2_SHA256})

CODE_REQUIRED = "verification_required"
CODE_INVALID = "verification_invalid"
CODE_EXPIRED = "verification_expired"
CODE_CONSUMED = "verification_consumed"
CODE_CONTEXT_MISMATCH = "verification_context_mismatch"
CODE_RATE_LIMITED = "verification_rate_limited"
CODE_UNAVAILABLE = "verification_unavailable"
CODE_SEND_UNKNOWN = "send_unknown"
CODE_SEND_THROTTLED = "send_throttled"
CODE_CONFLICTING_REQUEST = "send_request_conflict"
CODE_PAUSED = "send_paused"

FIELD_CHALLENGE_ID = "verification_challenge_id"
FIELD_PAYLOAD = "verification_payload"
FIELD_REQUEST_ID = "send_request_id"

EMAIL_CHANNEL = "email"
SMS_CHANNEL = "sms"

KIND_EMAIL = "email"
KIND_PHONE = "phone"

PRINCIPAL_MEMBER = "member"
PRINCIPAL_SESSION = "session"
PRINCIPAL_ANONYMOUS = "anonymous"

# Operations that may create or send a user-triggered verification code.
OP_EMAIL_AUTH_REQUEST_CODE = "email_auth.request_code"
OP_PHONE_AUTH_REQUEST_CODE = "phone_auth.request_code"
OP_LOGIN_REQUEST_CODE = "login.request_code"
OP_REGISTER = "register"
OP_REGISTER_RESEND_CODE = "register.resend_code"
OP_PASSWORD_RESET_REQUEST_CODE = "password_reset.request_code"
OP_CHANGE_PASSWORD_REQUEST_CODE = "change_password.request_code"
OP_DELETE_ACCOUNT_REQUEST_CODE = "delete_account.request_code"
OP_CONTACT_EMAIL_CREATE = "contact_email.create"
OP_CONTACT_EMAIL_REQUEST_VERIFICATION = "contact_email.request_verification"
OP_CONTACT_PHONE_REQUEST_VERIFICATION = "contact_phone.request_verification"
OP_EVENT_SEND_PHONE_CODE = "event.send_phone_code"
OP_ADMIN_LOGIN_REQUEST_CODE = "admin.login.request_code"
OP_ADMIN_LOGIN_REMEMBERED_CODE = "admin.login.remembered_code"
OP_ADMIN_LOGIN_RESEND = "admin.login.resend"

ALL_OPERATIONS = frozenset(
    {
        OP_EMAIL_AUTH_REQUEST_CODE,
        OP_PHONE_AUTH_REQUEST_CODE,
        OP_LOGIN_REQUEST_CODE,
        OP_REGISTER,
        OP_REGISTER_RESEND_CODE,
        OP_PASSWORD_RESET_REQUEST_CODE,
        OP_CHANGE_PASSWORD_REQUEST_CODE,
        OP_DELETE_ACCOUNT_REQUEST_CODE,
        OP_CONTACT_EMAIL_CREATE,
        OP_CONTACT_EMAIL_REQUEST_VERIFICATION,
        OP_CONTACT_PHONE_REQUEST_VERIFICATION,
        OP_EVENT_SEND_PHONE_CODE,
        OP_ADMIN_LOGIN_REQUEST_CODE,
        OP_ADMIN_LOGIN_REMEMBERED_CODE,
        OP_ADMIN_LOGIN_RESEND,
    }
)

AUTHENTICATED_OPERATIONS = frozenset(
    {
        OP_CHANGE_PASSWORD_REQUEST_CODE,
        OP_DELETE_ACCOUNT_REQUEST_CODE,
        OP_CONTACT_EMAIL_CREATE,
        OP_CONTACT_EMAIL_REQUEST_VERIFICATION,
        OP_CONTACT_PHONE_REQUEST_VERIFICATION,
        OP_EVENT_SEND_PHONE_CODE,
    }
)

SMS_OPERATIONS = frozenset(
    {
        OP_PHONE_AUTH_REQUEST_CODE,
        OP_CONTACT_PHONE_REQUEST_VERIFICATION,
        OP_EVENT_SEND_PHONE_CODE,
    }
)

# SMS hourly destination caps already live on PhoneVerificationChallenge.send_reserved_at.
# Email destination-hourly is owned by this service so it is cross-entry-point.
EMAIL_DESTINATION_HOURLY_OPERATIONS = ALL_OPERATIONS - SMS_OPERATIONS
