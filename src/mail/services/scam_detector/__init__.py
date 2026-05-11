"""Rule-based scam/fraud email detection heuristics."""

from __future__ import annotations

from typing import Any

from .checks import check_body, check_links, check_sender, check_structure, check_subject
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

    if total_score >= HIGH_THRESHOLD:
        risk_level = "high"
    elif total_score >= MEDIUM_THRESHOLD:
        risk_level = "medium"
    else:
        risk_level = "low"

    return {
        "risk_level": risk_level,
        "score": total_score,
        "reasons": reasons,
    }


__all__ = ["analyze_email"]
