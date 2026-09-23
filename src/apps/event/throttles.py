"""Per-view throttle classes for event endpoints.

Per project convention, DEFAULT_THROTTLE_CLASSES is never set globally (it would
throttle every view, including tests at 127.0.0.1); throttle classes are attached
per view and only the *rates* live in settings (DEFAULT_THROTTLE_RATES).

``PhoneCodeRequestThrottle`` is defined canonically in ``apps.authn.security.throttles``
(it caps SMS verification sends per authenticated user) and re-exported here so
event views can attach it without reaching across apps inline.
"""

from rest_framework.throttling import UserRateThrottle

from apps.authn.security.throttles import EmailCodeUserRequestThrottle, PhoneCodeRequestThrottle


class SecondaryEmailCodeVerifyThrottle(UserRateThrottle):
    """Apply the existing email verification rate to authenticated registrants."""

    scope = "email_code_verify"


__all__ = ["EmailCodeUserRequestThrottle", "PhoneCodeRequestThrottle", "SecondaryEmailCodeVerifyThrottle"]
