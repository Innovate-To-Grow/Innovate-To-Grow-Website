"""
The finer, per-view limits: each DRF throttle and counter an app keeps under its route scope, as a request-limit
scope with a ``parent`` (the route scope it sits under) and the identity ``view`` (the view keeps its own key; the
description says which). They seed ``RequestRateLimitPolicy`` rows like every scope, so staff edit them in the same
table and a change applies without a restart (``apps.core.services.request_limits.view_limits``).

Smart limiting applies to them too and takes priority over the manual limit: the limit is the seed × the parent
scope's Smart factor, clamped to the scope's floor; a P0 or fixed scope is never tightened for load. Every value
below is the rate in force before this feature (``DEFAULT_THROTTLE_RATES``, class constants and env vars) unless it
says "new". Sign-in and code limits are never keyed on the client IP (most users share one campus address).
"""

from .critical_view_scopes import P0_VIEW_SCOPES
from .view_seed import HOUR, MINUTE, _env_count, _view

P1_VIEW_SCOPES = {
    "view-contact-email-create": _view(
        "Add a contact email, per member", "p1", "member-write", 5, HOUR, "Per member (contact_email_create)."
    ),
    "view-contact-phone-create": _view(
        "Add a contact phone, per member",
        "p1",
        "member-write",
        5,
        HOUR,
        "New, mirrors contact emails. Per member (contact_phone_create).",
    ),
    "view-past-project-share": _view(
        "Create a project share, per member", "p1", "member-write", 10, MINUTE, "Per member (past_project_share)."
    ),
    "view-past-project-share-update": _view(
        "Edit a project share, per member",
        "p1",
        "member-write",
        120,
        MINUTE,
        "Per owner; each edit of a shared list is one request (past_project_share_update).",
    ),
    "view-registration-create": _view(
        "Event registration, per member",
        "p1",
        "member-send",
        20,
        HOUR,
        "New. Per member: registering or updating a registration, each of which emails the ticket.",
    ),
    "view-ticket-email-resend": _view(
        "Ticket email resend, per member",
        "p1",
        "member-send",
        10,
        HOUR,
        "New. Per member: resending a ticket email (each builds the barcode and calendar file and sends a mail).",
    ),
    "view-cli-read": _view("CLI reads, per member", "p1", "cli", 120, MINUTE, "Per staff member (cli_read)."),
    "view-cli-write": _view("CLI writes, per member", "p1", "cli", 60, MINUTE, "Per staff member (cli_write)."),
}

P2_VIEW_SCOPES = {
    "view-pageview-visitor": _view(
        "Page views, per visitor",
        "p2",
        "telemetry",
        120,
        MINUTE,
        "Per browser visitor id, never per IP (pageview_visitor; per process).",
    ),
    "view-pageview-legacy": _view(
        "Page views without a visitor id",
        "p2",
        "telemetry",
        600,
        MINUTE,
        "One shared bucket for page views without a usable visitor id (pageview_legacy; per process).",
    ),
    "view-pageview-total": _view(
        "Page views, everyone together",
        "p2",
        "telemetry",
        3_000,
        MINUTE,
        "Every accepted page view of a process (pageview_total).",
    ),
    "view-csp-report": _view(
        "CSP reports, per sender",
        "p2",
        "telemetry",
        _env_count("CSP_REPORT_RATE_LIMIT", 60),
        _env_count("CSP_REPORT_RATE_WINDOW_SECONDS", 60),
        "Per client address (seeded from CSP_REPORT_RATE_LIMIT / CSP_REPORT_RATE_WINDOW_SECONDS).",
    ),
}

P3_VIEW_SCOPES = {
    "view-ai-search": _view(
        "AI project search, per member", "p3", "ai", 10, MINUTE, "Per member (past_project_ai_search)."
    ),
    "view-assistant-chat": _view(
        "Assistant chat, per actor",
        "p3",
        "ai",
        6,
        MINUTE,
        "Per signed visitor or member, never per IP (public_assistant; per process). Token budgets still apply.",
    ),
    "view-assistant-legacy": _view(
        "Assistant chat without a visitor value",
        "p3",
        "ai",
        60,
        MINUTE,
        "One shared bucket for callers without a usable visitor value (public_assistant_legacy; per process).",
    ),
}

VIEW_SCOPES = {**P0_VIEW_SCOPES, **P1_VIEW_SCOPES, **P2_VIEW_SCOPES, **P3_VIEW_SCOPES}
