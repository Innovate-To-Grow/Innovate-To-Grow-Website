"""
Custom throttle classes for auth endpoints.

Policy: sign-in, email-link, verification-code and ALTCHA-challenge flows are NOT limited per client IP. Most
legitimate users (the campus network) share one public address, so a per-IP bucket throttles everyone at once
while barely slowing an attacker. Those flows are bounded by secrets (login-link and impersonation tokens),
per-destination cooldown and hourly caps, per-challenge attempt limits, the SMS daily budget and, for password
login, the identifier-keyed failure lockout in ``apps.authn.services.login_guard``. Do not add an anonymous
per-IP throttle to those views. (The mail app's one-click unsubscribe and resubscribe pages are likewise gated
only by their signed tokens and unthrottled.)

What remains here is deliberate: per-authenticated-user throttles (a user is not a shared bucket), the anonymous
throttle classes still attached to ``IsAuthenticated`` views, where they are a no-op, and the per-IP SMS request
throttle, which is only a FALLBACK: ``sms_request_throttles()`` applies it solely while no global SMS daily budget
is configured (see there).
"""

import logging

from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

from apps.core.utils.throttle_cache import throttle_cache

logger = logging.getLogger(__name__)


class ContactEmailCreateThrottle(UserRateThrottle):
    """Throttle for adding contact emails: 5 requests per hour."""

    scope = "contact_email_create"


class EmailCodeVerifyThrottle(AnonRateThrottle):
    """Anonymous throttle attached to ``IsAuthenticated`` verify views, where it is a no-op.

    Public verify endpoints deliberately do not use it: their guess limit is the per-challenge attempt cap.
    """

    scope = "email_code_verify"


class PhoneCodeRequestThrottle(UserRateThrottle):
    """Per-authenticated-user cap on SMS verification-code sends.

    Each send spends real AWS SNS budget on a caller-supplied destination, and
    the service-level cap is per destination number (bypassable by rotating
    numbers). An ``AnonRateThrottle`` is a no-op for authenticated callers, so a
    ``UserRateThrottle`` is required to bound toll-fraud / SMS pumping.
    """

    scope = "phone_code_request"


class PhoneAuthCodeRequestThrottle(AnonRateThrottle):
    """Per-IP cap on the PUBLIC SMS request endpoints (passwordless phone auth, password reset by phone).

    Each request can spend real AWS SNS budget on a caller-supplied destination, and the service-level cap in
    ``sns_verify`` is per destination number (bypassable by rotating numbers). This is a fallback only: attach it
    through ``sms_request_throttles()``, never unconditionally.
    """

    scope = "phone_auth_code_request"
    # Keyed on the client address DRF resolves from X-Forwarded-For. Production trusts only the entry the ALB
    # appended (``REST_FRAMEWORK["NUM_PROXIES"]``), but with it unset (local, CI) that is the whole caller-supplied
    # string, so the key space is not bounded: its history stays out of the file cache. Either way it is a speed
    # bump, not a bound (per process, one bucket per address). While it applies (no SMS daily budget configured),
    # enforce mode sends no SMS at all and observe mode is bounded only per number: configure ``sms_daily_limit``.
    cache = throttle_cache


def sms_request_throttles() -> list:
    """Throttles for a public request that sends an SMS: the per-IP one ONLY while no SMS daily budget exists.

    With a global SMS daily budget configured (``load_settings().sms_daily_limit``), every public SMS send reserves
    against it (in observe and enforce mode alike; pause sends nothing), and each number keeps its own cooldown and
    hourly cap, so spend is bounded without keying anything on the client IP (the campus shares one address).
    Without a budget the per-IP throttle is the only aggregate speed bump left (a caller with many addresses gets
    a bucket per address, so it is not a bound), so it stays. A settings error keeps it too: fail safe.
    """
    from apps.authn.services.send_verification.config import load_settings

    try:
        budget_configured = bool(load_settings().sms_daily_limit)
    except Exception as exc:  # noqa: BLE001 - any failure to read the policy keeps the throttle.
        logger.warning("SMS budget unreadable (%s); keeping the per-IP SMS throttle", type(exc).__name__)
        budget_configured = False
    return [] if budget_configured else [PhoneAuthCodeRequestThrottle()]


class EmailCodeUserRequestThrottle(UserRateThrottle):
    """Per-authenticated-user cap on email verification-code sends.

    An ``AnonRateThrottle`` keys on ``None`` for authenticated requests, so on
    an ``IsAuthenticated`` resend endpoint it never throttles — letting a
    logged-in caller bomb an attacker-supplied address (and burn SES budget).
    This per-user throttle actually applies.
    """

    scope = "email_code_user_request"
