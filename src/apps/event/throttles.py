"""Per-view throttle classes for event endpoints.

Per project convention, DEFAULT_THROTTLE_CLASSES is never set globally (it would
throttle every view, including tests at 127.0.0.1); throttle classes are attached
per view. Each rate is a request-limit policy (``policy_scope``), read live, so staff
edit it in the admin without a restart (``apps.core.services.request_limits.view_limits``).

``PhoneCodeRequestThrottle``, ``EmailCodeUserRequestThrottle`` and ``EmailCodeVerifyThrottle``
are defined canonically in ``apps.authn.security.throttles`` and re-exported here so event
views can attach them without reaching across apps inline.
"""

from apps.authn.security.throttles import (
    EmailCodeUserRequestThrottle,
    EmailCodeVerifyThrottle,
    PhoneCodeRequestThrottle,
)
from apps.core.services.request_limits.view_limits import MemberRateThrottle


class SecondaryEmailCodeVerifyThrottle(EmailCodeVerifyThrottle):
    """The member's code-check bucket for the event's secondary email code (shared with every signed-in code)."""


class PhoneCodeVerifyThrottle(EmailCodeVerifyThrottle):
    """The member's code-check bucket for the event's phone code (it had no limit of its own)."""


class RegistrationCreateThrottle(MemberRateThrottle):
    """Registering for an event (or updating the registration), per member: each one emails the ticket."""

    scope = "event_registration_create"
    policy_scope = "view-registration-create"


class TicketEmailResendThrottle(MemberRateThrottle):
    """Resending a ticket email, per member: each one builds the barcode and calendar file and sends a mail."""

    scope = "event_ticket_email_resend"
    policy_scope = "view-ticket-email-resend"


__all__ = [
    "EmailCodeUserRequestThrottle",
    "PhoneCodeRequestThrottle",
    "PhoneCodeVerifyThrottle",
    "RegistrationCreateThrottle",
    "SecondaryEmailCodeVerifyThrottle",
    "TicketEmailResendThrottle",
]
