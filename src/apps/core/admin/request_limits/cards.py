"""The scope cards of Site Settings → Request Limits, built from ``request_limits.reporting.overview`` (the tier summary is in
``summary``).

Per scope: ``Now: 3,000 / minute per caller · everyone together 12,000 / minute · Smart ×1.00``, the per-process
share when counters are per process, why Smart set the factor (the controller's last decision and its signals) and
the recent 429s. Nothing here computes a limit.
"""

from dataclasses import dataclass
from datetime import datetime

PERIODS = {1: "second", 60: "minute", 3_600: "hour", 86_400: "day"}


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
