"""The P0 (critical) route scopes: user-initiated sign-in and verification, must-not-fail operations. Smart never
sheds them for load; only their abuse rules apply. The keys are described in ``scopes``."""

from .scope_seed import _scope

P0_SCOPES = {
    "auth-sign-in": _scope(
        "Sign-in and password checks",
        "p0",
        "destination",
        20,
        global_cap=1_200,
        description="Password sign-in (site and admin), change-password, maintenance bypass, staff invitations and "
        "the CLI token exchange. Each identifier is also bounded by the sign-in lockout.",
        source=240,
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
        source=120,
    ),
    "auth-code-verify": _scope(
        "Verification code check",
        "p0",
        "destination",
        60,
        global_cap=1_800,
        description="Entering a code; each challenge also has its own attempt cap (today 60/min per member).",
        source=360,
    ),
    "auth-email-link": _scope(
        "Email link and token exchange",
        "p0",
        "destination",
        30,
        global_cap=1_200,
        description="Magic-link sign-in, impersonation hand-off and the legacy viewer's token exchange.",
        source=240,
    ),
    "auth-challenge": _scope(
        "Anti-abuse challenge",
        "p0",
        "member",
        120,
        global_cap=3_000,
        description="ALTCHA proof-of-work challenges, their status polls and the sign-in public key.",
        source=600,
    ),
    "auth-token-refresh": _scope(
        "Token refresh",
        "p0",
        "global",
        6_000,
        global_cap=6_000,
        fixed=True,
        description="Exchanging a refresh token; a refused refresh signs members out of member-only pages.",
        source=1_200,
    ),
    "auth-session": _scope(
        "Session check",
        "p0",
        "member",
        300,
        global_cap=12_000,
        fixed=True,
        description="The signed-in check every page makes.",
        source=2_400,
    ),
    "checkin-scan": _scope(
        "Event check-in scan",
        "p0",
        "session",
        1_200,
        fixed=True,
        description="Scanning and undoing at the event door.",
        source=120,
    ),
    "webhook-ses": _scope(
        "Amazon SES event webhook",
        "p0",
        "ip",
        3_000,
        fixed=True,
        # No aggregate cap: unsigned junk from many addresses must never use up the allowance of the real SNS
        # deliveries; each sender has its own bucket, and the view counts signed and rejected calls apart.
        description="Bounce, complaint and delivery events (600/min per IP and process before; a campaign sends more "
        "than that site-wide); they feed the delivery-rate controller.",
    ),
}
