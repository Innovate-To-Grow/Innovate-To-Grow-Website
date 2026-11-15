"""The P0 (critical) per-view limits: never tightened for load. The keys are described in ``view_scopes``."""

from .view_seed import HOUR, MINUTE, _view

P0_VIEW_SCOPES = {
    "view-code-send-email": _view(
        "Email code send, per member",
        "p0",
        "auth-code-send",
        5,
        MINUTE,
        "Per signed-in member: account, contact-email and event email codes (DRF scope email_code_user_request).",
    ),
    "view-code-send-sms": _view(
        "SMS code send, per member",
        "p0",
        "auth-code-send",
        5,
        MINUTE,
        "Per signed-in member: account, contact-phone and event SMS codes; each costs SNS money (phone_code_request).",
    ),
    "view-code-send-sms-ip": _view(
        "Public SMS code send, per IP (fallback)",
        "p0",
        "auth-code-send",
        5,
        MINUTE,
        "Per client IP, only while no SMS daily budget is configured: the public phone sign-in and phone password "
        "reset (phone_auth_code_request).",
    ),
    "view-code-verify": _view(
        "Code check, per member",
        "p0",
        "auth-code-verify",
        60,
        MINUTE,
        "Per signed-in member, one bucket for every code a member enters: account changes, contact email / phone "
        "and event email / phone codes (email_code_verify).",
    ),
    "view-change-password": _view(
        "Change password, per member",
        "p0",
        "auth-sign-in",
        10,
        HOUR,
        "New. Per signed-in member: changing the password with the current one (each try checks a password hash).",
    ),
    "view-invitation": _view(
        "Staff invitation acceptance, per invitation",
        "p0",
        "auth-sign-in",
        10,
        HOUR,
        "Per invitation: form submissions on one staff invitation link.",
    ),
    "view-maintenance-bypass": _view(
        "Maintenance bypass failures",
        "p0",
        "auth-sign-in",
        20,
        15 * MINUTE,
        "New. Wrong maintenance-bypass passwords from everyone together; once reached, every bypass attempt is "
        "refused until the period ends (one shared password, so one shared lockout; never per IP).",
    ),
    "view-ses-events": _view(
        "Signed SES events, per sender",
        "p0",
        "webhook-ses",
        600,
        MINUTE,
        "Per sending address, counted only once the SNS signature is verified (ses_events).",
        fixed=True,
    ),
    "view-ses-rejected": _view(
        "Rejected SES webhook calls, per sender",
        "p0",
        "webhook-ses",
        60,
        MINUTE,
        "New. Per sending address: calls whose SNS signature fails. Counted apart from signed deliveries, so junk "
        "never uses up their allowance.",
        fixed=True,
    ),
}
