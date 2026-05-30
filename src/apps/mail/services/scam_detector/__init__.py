"""Rule-based scam/fraud email detection heuristics."""

from __future__ import annotations

from typing import Any

from .checks import check_body, check_links, check_sender, check_structure, check_subject, link_warning_details
from .patterns import HIGH_THRESHOLD, MEDIUM_THRESHOLD


def analyze_email(msg: dict[str, Any]) -> dict[str, Any]:
    all_findings: list[tuple[int, str]] = []
    all_findings.extend(check_sender(msg))
    all_findings.extend(check_subject(msg))
    all_findings.extend(check_body(msg))
    all_findings.extend(check_links(msg))
    all_findings.extend(check_structure(msg))

    total_score = sum(score for score, _ in all_findings)
    reasons = [reason for _, reason in all_findings]
    link_warnings = link_warning_details(msg)

    if total_score >= HIGH_THRESHOLD:
        risk_level = "high"
    elif total_score >= MEDIUM_THRESHOLD:
        risk_level = "medium"
    else:
        risk_level = "low"

    return {
        "risk_level": risk_level,
        "score": total_score,
        "score_percent": _score_percent(total_score),
        "reasons": reasons,
        "findings": [_format_finding(score, reason) for score, reason in sorted(all_findings, reverse=True)],
        "summary": _risk_summary(risk_level, len(all_findings), len(link_warnings)),
        "recommendation": _recommendation(risk_level, has_link_warning=bool(link_warnings)),
        "link_warnings": link_warnings,
    }


def _score_percent(score: int) -> int:
    if score <= 0:
        return 0
    return min(round((score / HIGH_THRESHOLD) * 100), 100)


def _format_finding(score: int, reason: str) -> dict[str, Any]:
    return {
        "category": _category_for_reason(reason),
        "impact": _impact_label(score),
        "score": score,
        "reason": reason,
    }


def _category_for_reason(reason: str) -> str:
    reason_lower = reason.lower()
    if any(term in reason_lower for term in ("link", "url", "ip address", "shortened")):
        return "Link integrity"
    if any(term in reason_lower for term in ("sender", "display name", "freemail", "email domain")):
        return "Sender identity"
    if "subject" in reason_lower:
        return "Subject language"
    if any(term in reason_lower for term in ("body", "greeting", "monetary", "personal", "financial")):
        return "Message content"
    if any(term in reason_lower for term in ("html", "hidden", "plain-text", "zero-size")):
        return "Message structure"
    return "Security signal"


def _impact_label(score: int) -> str:
    if score >= 4:
        return "Critical"
    if score == 3:
        return "High"
    if score == 2:
        return "Medium"
    return "Low"


def _risk_summary(risk_level: str, finding_count: int, link_warning_count: int) -> str:
    if risk_level == "high":
        return "Multiple high-risk fraud signals were detected. Treat this message as unsafe until verified."
    if link_warning_count:
        link_label = "link" if link_warning_count == 1 else "links"
        verb = "needs" if link_warning_count == 1 else "need"
        return f"{link_warning_count} suspicious {link_label} {verb} review because the displayed domain differs from the destination."
    if risk_level == "medium":
        signal_label = "signal" if finding_count == 1 else "signals"
        return f"{finding_count} security {signal_label} need review before clicking links or replying."
    return "No obvious fraud indicators were detected by the automated checks."


def _recommendation(risk_level: str, *, has_link_warning: bool) -> str:
    if risk_level == "high":
        return "Do not click links or open attachments. Verify the sender through a separate trusted channel."
    if has_link_warning:
        return "Open the official site directly or verify with the sender before using the embedded link."
    if risk_level == "medium":
        return "Verify the sender and destination before taking action from this message."
    return "Continue normal handling, but review unusual requests manually."


__all__ = ["analyze_email"]
