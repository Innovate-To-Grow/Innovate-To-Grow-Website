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
- ``source_cap``: a per-IP **flood ceiling** for callers without a verified identity (anonymous, or an unverified
  CLI token) in a scope not keyed on the IP. Their own key is missing or one they choose (a destination), so
  without it one client could fill the aggregate cap and refuse everyone; with it a single source adds at most this
  many requests to the aggregate, and going over it is a strike against that source. Sized far above any campus
  burst; a deployer maximum like ``global_cap`` (settings only, shown in the admin).
- ``fixed``: Smart never tightens the scope (webhooks, token refresh, session check, the check-in desk).

Values marked "today" are the rates in force before this feature (``DEFAULT_THROTTLE_RATES`` and class constants);
the per-view limits (``view_scopes.py``) keep them as finer limits underneath. Everything else is a new, generous default sized
to stop floods, not people: the busiest real pattern (the catalog loading ten 100-row pages, a staff member
scanning tickets every second) stays far below it.
"""

from .critical_scopes import P0_SCOPES
from .scope_seed import _scope
from .view_scopes import VIEW_SCOPES

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
    "member-read": _scope("Member page data", "p1", "member", 600, global_cap=6_000, source=600),
    "member-write": _scope("Member changes", "p1", "member", 120, global_cap=1_200, source=120),
    "member-send": _scope(
        "Member actions that send email",
        "p1",
        "member",
        10,
        global_cap=300,
        description="Event registration and ticket resend.",
        source=30,
    ),
    "staff-admin": _scope("Admin pages", "p1", "session", 600, global_cap=6_000, source=600),
    "cli": _scope(
        "i2g-admin CLI",
        "p1",
        "cli",
        300,
        global_cap=3_000,
        description="The /admin-api/ surface (per-member read 120/min and write 60/min today, kept underneath).",
        source=600,
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
        source=60,
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
        source=120,
    ),
    "checkin-status": _scope(
        "Check-in desk status",
        "p2",
        "session",
        300,
        fixed=True,
        description="The check-in console's status poll (every 2 s per open console).",
        source=120,
    ),
}

P3_SCOPES = {
    "public-heavy": _scope(
        "Full-list catalog reads",
        "p3",
        "ip",
        60,
        global_cap=1_200,
        description="Whole-catalog lists in one response (/projects/past-all/).",
    ),
    "ai": _scope(
        "AI search and assistant",
        "p3",
        "ip",
        300,
        global_cap=600,
        # Per IP only a flood ceiling: a classroom shares one address, and the per-actor limits underneath are the
        # per-person ones (an IP bucket at their size would let one classroom lock everybody out).
        description="Bedrock calls; the per-actor limits (6/min chat, 10/min search) and token budgets stay.",
    ),
    "staff-bulk": _scope(
        "Admin bulk, export and external calls",
        "p3",
        "session",
        60,
        global_cap=600,
        description="Exports, imports, uploads, sheet and feed syncs, campaign sends, admin AI.",
        source=60,
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
