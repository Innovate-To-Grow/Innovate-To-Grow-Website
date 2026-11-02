"""The cards and summary lines of Site Settings → Request Limits, built from ``request_limits.overview``.

Per scope: ``Now: 3,000 / minute per caller · everyone together 12,000 / minute · Smart ×1.00``, the per-process
share when counters are per process, why Smart set the factor (the controller's last decision and its signals) and
the recent 429s. The summary says which tiers Smart is shedding, this process's last assessment, its slots (the ones
kept for P0 among them) and the counter mode. Nothing here computes a limit.
"""

from dataclasses import dataclass
from datetime import datetime

PERIODS = {1: "second", 60: "minute", 3_600: "hour", 86_400: "day"}
TIER_STATES = {
    "protected": "protected (never tightened for load, only by its abuse limits)",
    "full": "full baseline",
    "shedding": "Smart is shedding it",
    "recovering": "recovering",
}
COUNTER_MODES = {
    "shared": "Shared counters (Redis): every process counts in one atomic counter, so each limit holds site-wide.",
    "local": (
        "Per-process estimate: no shared cache is configured, so each web process counts on its own and allows its "
        "share of every limit (the limit ÷ the live processes, rounded up). Live processes now (heartbeat rows): "
        "{processes}. Recent 429s are this process's."
    ),
}
TIER_COPY = (
    (
        "P0 critical",
        "What a person has just asked for and must not fail: verification codes they requested (email and SMS), "
        "checking a code, sign-in, email links, password reset, token refresh, the session check, the anti-abuse "
        "challenge, event check-in and the SES webhook. Smart limit never tightens P0 for load and keeps request "
        "slots for it, so codes still arrive while the site is busy. Its abuse limits still apply: code cooldowns, "
        "hourly caps, the SMS daily budget, attempt caps, the sign-in lockout, and a growing block for a caller "
        "refused again and again. A code request with neither a sign-in nor a valid anti-abuse proof is not P0.",
    ),
    ("P1 interactive", "What a person is waiting for on screen: page data, form submits, registrations, admin pages."),
    ("P2 background", "Automatic and repeating requests: status polling, page-view telemetry, CSP reports."),
    ("P3 heavy", "Expensive or bulk requests: full catalog lists, AI search and assistant, exports, 404 scanners."),
)


@dataclass(frozen=True)
class ScopeCard:
    scope: str
    label: str
    description: str
    tier: str
    parent_label: str
    form: object
    lines: tuple[str, ...]
    manual_locked: bool
    advanced_open: bool


def per_period(count: int, period: int) -> str:
    unit = PERIODS.get(period)
    return f"{count:,} / {unit}" if unit else f"{count:,} / {period:,} s"


def clock(moment: str | None) -> str:
    if not moment:
        return ""
    try:
        return datetime.fromisoformat(moment).strftime("%H:%M:%S UTC")
    except ValueError:
        return ""


def _headline(view) -> str:
    if not view.enabled:
        return "Not limited: this scope is switched off."
    if view.parent is not None:
        return f"Now: {per_period(view.per_identity, view.period)} (counted per the view's own key)"
    parts = []
    if view.identity != "global":
        parts.append(f"{per_period(view.per_identity, view.period)} per caller")
    if view.global_cap is not None:
        parts.append(f"everyone together {per_period(view.global_cap, view.period)}")
    if view.source_cap is not None:
        parts.append(f"per anonymous source {per_period(view.source_cap, view.period)}")
    parts.append(f"Smart ×{view.factor:.2f}" if view.factor is not None else "manual limit")
    return "Now: " + " · ".join(parts)


def smart_line(view, parent_label: str = "") -> str:
    """Why the factor is what it is."""
    if not view.smart:
        return "Smart limit is off: the manual limit applies."
    if view.tier == "p0":
        return "P0: Smart limit never tightens it for load; only its abuse limits apply."
    if view.fixed:
        return "Fixed: Smart limit never tightens it."
    follows = f" (follows {parent_label})" if parent_label else ""
    decision = view.decision
    if not decision:
        return f"Smart ×{view.factor:.2f} of the baseline{follows}: no Smart change yet."
    action = "cut" if decision.get("action") == "shed" else "restored"
    when = clock(decision.get("at"))
    reasons = "; ".join(decision.get("reasons") or []) or decision.get("pressure", "")
    because = f" because of {reasons}" if action == "cut" and reasons else ""
    return f"Smart ×{view.factor:.2f} of the baseline{follows}: {action} at {when}{because}."


def refused_line(view, minutes: int) -> str:
    if view.refused is None:
        return ""
    limiter, own = view.refused.get("limiter", 0), view.refused.get("view", 0)
    return f"429s in the last {minutes} min: {limiter + own:,} ({limiter:,} by this limiter, {own:,} by the view's own limits)"


def scope_lines(view, data: dict, parent_label: str = "") -> tuple[str, ...]:
    lines = [_headline(view)]
    if view.enabled:
        if view.per_process is not None and data["processes"] > 1 and view.identity != "global":
            lines.append(
                f"Per process: {per_period(view.per_process, view.period)} per caller ({data['processes']} processes)"
            )
        lines.append(smart_line(view, parent_label))
    lines.append(refused_line(view, data["history_minutes"]))
    return tuple(line for line in lines if line)


def _labels(forms) -> dict[str, str]:
    return {scope: form.instance.label for scope, form in forms.items()}


def build_cards(forms: dict, data: dict) -> list[ScopeCard]:
    labels = _labels(forms)
    cards = []
    for scope, form in forms.items():
        view = data["scopes"][scope]
        parent_label = labels.get(view.parent, view.parent or "")
        cards.append(
            ScopeCard(
                scope=scope,
                label=form.instance.label,
                description=form.instance.description,
                # The stored tier (a rejected post must not move the card).
                tier=view.tier,
                parent_label=parent_label,
                form=form,
                lines=scope_lines(view, data, parent_label),
                manual_locked=form.lock_manual_limit(),
                advanced_open=any(bound.errors for bound in form.advanced_fields()),
            )
        )
    return cards


def tier_groups(cards: list[ScopeCard], data: dict) -> list[dict]:
    """One section per tier (by the tier saved on each row): its explanation, Smart's state, route and per-view
    cards."""
    states = {item["tier"]: item for item in data["tiers"]}
    groups = []
    for (label, copy), tier in zip(TIER_COPY, ("p0", "p1", "p2", "p3"), strict=True):
        members = [card for card in cards if card.tier == tier]
        views = [card for card in members if card.parent_label]
        groups.append(
            {
                "tier": tier,
                "label": label,
                "copy": copy,
                "state": tier_line(states[tier]),
                "routes": [card for card in members if not card.parent_label],
                "views": views,
                "views_open": any(card.form.errors for card in views),
            }
        )
    return groups


def tier_line(item: dict) -> str:
    line = f"{item['label']}: {TIER_STATES[item['state']]}"
    if item["below"]:
        line += f" ({len(item['below'])} of {item['scopes']} scopes below baseline, lowest ×{item['lowest']:.2f})"
    return line


def assessment_line(last: dict) -> str:
    if not last:
        return "Smart limit has not assessed a signal window in this process yet."
    reasons = "; ".join(last.get("reasons") or [])
    action = {"shed": "shed", "restore": "restore"}.get(last.get("action"), "hold")
    target = f" {last['tier'].upper()}" if last.get("tier") and action != "hold" else ""
    detail = f": {reasons}" if reasons else ""
    return (
        f"Last assessment in this process ({clock(last.get('at'))}): {last.get('pressure')}{detail} → {action}{target}."
    )


def slots_line(slots: dict) -> str:
    limits = slots["tier_limits"]
    return (
        f"Request slots in this process: {slots['in_flight']} of {slots['concurrency']} in use. P1 may fill "
        f"{limits['p1']}, P2 {limits['p2']}, P3 {limits['p3']}; {slots['p0_reserved']} are kept for P0 "
        f"({slots['p0_reserved_in_use']} in use)."
    )


def summary(data: dict) -> dict:
    return {
        "enabled": data["enabled"],
        "counter_mode": data["counter_mode"],
        "processes": data["processes"],
        "counter_line": COUNTER_MODES[data["counter_mode"]].format(processes=data["processes"]),
        "tier_lines": [tier_line(item) for item in data["tiers"]],
        "tier_states": {item["tier"]: tier_line(item) for item in data["tiers"]},
        "shedding": [item["tier"] for item in data["tiers"] if item["state"] == "shedding"],
        "assessment_line": assessment_line(data["last_assessment"]),
        "slots_line": slots_line(data["slots"]),
        "slots": data["slots"],
    }


def status_payload(data: dict, labels: dict[str, str]) -> dict:
    """What ``request-limits/status/`` returns: the summary and every scope's lines."""
    scopes = []
    for scope, view in data["scopes"].items():
        parent_label = labels.get(view.parent, view.parent or "")
        scopes.append(
            {
                "scope": scope,
                "tier": view.tier,
                "mode": view.mode,
                "factor": view.factor,
                "per_identity": view.per_identity,
                "per_process": view.per_process,
                "global_cap": view.global_cap,
                "period_seconds": view.period,
                "refused": view.refused,
                "lines": list(scope_lines(view, data, parent_label)),
            }
        )
    return {"summary": summary(data), "scopes": scopes}
