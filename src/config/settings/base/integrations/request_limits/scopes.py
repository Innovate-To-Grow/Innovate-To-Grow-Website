"""
The request-limit scopes: every endpoint group, its priority tier, who a request counts against, and its seeds.

Each scope seeds one ``RequestRateLimitPolicy`` row (the copy staff edit later). ``requests`` per ``period_seconds``
is both the manual limit's seed and the **baseline** Smart limiting scales: with Smart on (the default everywhere)
the limit is ``baseline × factor`` and the manual value is not read. ``identity_ceiling`` and ``global_cap`` are
deployer maximums: the admin can lower them, never raise them (a ``REQUEST_RATE_LIMITS_OVERRIDES`` change can).

Keys:

- ``tier``: ``p0`` critical (user-initiated sign-in and verification, must-not-fail operations; never shed for
  load, only its abuse rules apply), ``p1`` interactive, ``p2`` background / polling / telemetry, ``p3`` heavy /
  bulk / AI / scanner traffic. Under overload Smart sheds P3 first, then P2, then P1.
- ``identity``: what one bucket counts. ``member`` = the verified JWT member or the signed-in staff user, never an
  IP; ``session`` = the signed-in (admin) user; ``cli`` = the CLI token; ``ip`` = the signed-in user if any, else
  the client IP; ``destination`` = the key an app registers for the scope (the code's destination), else the member;
  ``global`` = no per-caller bucket, only ``global_cap``; ``view`` = a per-view limit (``view_scopes.py``) whose
  view keeps its own key. Sign-in and code flows are never keyed on the IP: most users share one campus address
  (see ``config/settings/base/integrations/api``).
- ``fixed``: Smart never tightens the scope (webhooks, token refresh, session check, the check-in desk).

Values marked "today" are the rates in force before this feature (``DEFAULT_THROTTLE_RATES`` and class constants);
the per-view limits (``view_scopes.py``) keep them as finer limits underneath. Everything else is a new, generous default sized
to stop floods, not people: the busiest real pattern (the catalog loading ten 100-row pages, a staff member
scanning tickets every second) stays far below it.
"""

from .view_scopes import VIEW_SCOPES

MINUTE = 60


def _scope(label, tier, identity, requests, *, period=MINUTE, global_cap=None, ceiling=None, fixed=False, **extra):
    return {
        "label": label,
        "description": extra.pop("description", ""),
        "tier": tier,
        "identity": identity,
        "requests": requests,
        "period_seconds": period,
        "smart_enabled": True,
        # None: the tier's floor (``TIERS``).
        "smart_floor": extra.pop("smart_floor", None),
        "fixed": fixed,
        "enabled": True,
        "identity_ceiling": ceiling,
        "global_cap": global_cap,
    }


P0_SCOPES = {
    "auth-sign-in": _scope(
        "Sign-in and password checks",
        "p0",
        "destination",
        20,
        global_cap=1_200,
        description="Password sign-in (site and admin), change-password, maintenance bypass, staff invitations and "
        "the CLI token exchange. Each identifier is also bounded by the sign-in lockout.",
    ),
    "auth-code-send": _scope(
        "Verification code send",
        "p0",
        "destination",
        10,
        global_cap=600,
        description="Email / SMS codes a person asked for (sign-in, registration, password reset, account changes, "
        "event phone and email). Destination cooldowns, hourly caps and the SMS daily budget still apply "
        "(today 5/min per member).",
    ),
    "auth-code-verify": _scope(
        "Verification code check",
        "p0",
        "destination",
        60,
        global_cap=1_800,
        description="Entering a code; each challenge also has its own attempt cap (today 60/min per member).",
    ),
    "auth-email-link": _scope(
        "Email link and token exchange",
        "p0",
        "destination",
        30,
        global_cap=1_200,
        description="Magic-link sign-in, impersonation hand-off and the legacy viewer's token exchange.",
    ),
    "auth-challenge": _scope(
        "Anti-abuse challenge",
        "p0",
        "member",
        120,
        global_cap=3_000,
        description="ALTCHA proof-of-work challenges, their status polls and the sign-in public key.",
    ),
    "auth-token-refresh": _scope(
        "Token refresh",
        "p0",
        "global",
        6_000,
        global_cap=6_000,
        fixed=True,
        description="Exchanging a refresh token; a refused refresh signs members out of member-only pages.",
    ),
    "auth-session": _scope(
        "Session check",
        "p0",
        "member",
        300,
        global_cap=12_000,
        fixed=True,
        description="The signed-in check every page makes.",
    ),
    "checkin-scan": _scope(
        "Event check-in scan",
        "p0",
        "session",
        1_200,
        fixed=True,
        description="Scanning and undoing at the event door.",
    ),
    "webhook-ses": _scope(
        "Amazon SES event webhook",
        "p0",
        "ip",
        600,
        fixed=True,
        # No aggregate cap: unsigned junk from many addresses must never use up the allowance of the real SNS
        # deliveries; each sender has its own bucket, and the view counts signed and rejected calls apart.
        description="Bounce and complaint events (today 600/min per IP); they feed the delivery-rate controller.",
    ),
}

P1_SCOPES = {
    "public-read": _scope(
        "Public page data",
        "p1",
        "ip",
        3_000,
        global_cap=12_000,
        description="Anonymous reads. The per-IP ceiling only stops single-source floods (a campus shares one IP).",
    ),
    "public-write": _scope("Public form submit", "p1", "ip", 120, global_cap=1_200),
    "member-read": _scope("Member page data", "p1", "member", 600, global_cap=6_000),
    "member-write": _scope("Member changes", "p1", "member", 120, global_cap=1_200),
    "member-send": _scope(
        "Member actions that send email",
        "p1",
        "member",
        10,
        global_cap=300,
        description="Event registration and ticket resend.",
    ),
    "staff-admin": _scope("Admin pages", "p1", "session", 600, global_cap=6_000),
    "cli": _scope(
        "i2g-admin CLI",
        "p1",
        "cli",
        300,
        global_cap=3_000,
        description="The /admin-api/ surface (per-member read 120/min and write 60/min today, kept underneath).",
    ),
    "tokenized-link": _scope("Links with a token", "p1", "ip", 60, global_cap=600),
    "legacy-proxy": _scope("Legacy site viewer", "p1", "ip", 1_200, global_cap=6_000),
}

P2_SCOPES = {
    "auth-code-unproven": _scope(
        "Code requests without a valid proof",
        "p2",
        "global",
        300,
        global_cap=300,
        description="A code request that neither comes from a signed-in person nor carries a valid anti-abuse "
        "proof is not promoted to P0: it is counted here, together, and shed like background traffic.",
    ),
    "public-background": _scope(
        "Public background requests",
        "p2",
        "ip",
        600,
        global_cap=6_000,
        description="Embed host list refresh, assistant settings, sitemap.",
    ),
    "telemetry": _scope(
        "Page views and CSP reports",
        "p2",
        "ip",
        300,
        global_cap=6_000,
        description="Per-visitor 120/min and site 3,000/min page-view caps stay underneath.",
    ),
    "staff-polling": _scope(
        "Admin status polling",
        "p2",
        "session",
        300,
        description="Campaign and SMS send status, dashboards data, delivery-rate status, CMS live preview.",
    ),
    "checkin-status": _scope(
        "Check-in desk status",
        "p2",
        "session",
        300,
        fixed=True,
        description="The check-in console's status poll (every 2 s per open console).",
    ),
}

P3_SCOPES = {
    "public-heavy": _scope(
        "Full-list catalog reads",
        "p3",
        "ip",
        60,
        global_cap=1_200,
        description="Whole-catalog lists (/projects/all/, /projects/past-all/).",
    ),
    "ai": _scope(
        "AI search and assistant",
        "p3",
        "ip",
        60,
        global_cap=600,
        description="Bedrock calls; the per-actor limits (6/min chat, 10/min search) and token budgets stay.",
    ),
    "staff-bulk": _scope(
        "Admin bulk, export and external calls",
        "p3",
        "session",
        60,
        global_cap=600,
        description="Exports, imports, uploads, sheet and feed syncs, campaign sends, admin AI.",
    ),
    "not-found": _scope(
        "Unmatched paths (404)",
        "p3",
        "ip",
        120,
        description="Requests for paths that do not exist: mostly scanners.",
    ),
}

SCOPES = {**P0_SCOPES, **P1_SCOPES, **P2_SCOPES, **P3_SCOPES, **VIEW_SCOPES}
