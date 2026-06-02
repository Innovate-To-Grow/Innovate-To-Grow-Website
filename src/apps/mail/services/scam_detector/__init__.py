"""Rule-based scam/fraud email detection heuristics."""

from __future__ import annotations

from typing import Any

from .checks import (
    check_address_alignment,
    check_authentication,
    check_body,
    check_links,
    check_sender,
    check_structure,
    check_subject,
    link_warning_details,
)
from .patterns import BRAND_NAMES, HIGH_THRESHOLD, MEDIUM_THRESHOLD

LLM_REVIEW_CACHE_TTL = 1800


def analyze_email(
    msg: dict[str, Any],
    *,
    brands: list[str] | None = None,
    medium_threshold: int = MEDIUM_THRESHOLD,
    high_threshold: int = HIGH_THRESHOLD,
) -> dict[str, Any]:
    """Deterministic rule scoring. Pure + DB-free; config is injected by assess_email."""
    brands = brands if brands is not None else BRAND_NAMES
    all_findings: list[tuple[int, str]] = []
    all_findings.extend(check_sender(msg, brands))
    all_findings.extend(check_subject(msg))
    all_findings.extend(check_body(msg))
    all_findings.extend(check_links(msg, brands))
    all_findings.extend(check_structure(msg))
    all_findings.extend(check_authentication(msg))
    all_findings.extend(check_address_alignment(msg))

    total_score = sum(score for score, _ in all_findings)
    reasons = [reason for _, reason in all_findings]
    link_warnings = link_warning_details(msg)

    if total_score >= high_threshold:
        risk_level = "high"
    elif total_score >= medium_threshold:
        risk_level = "medium"
    else:
        risk_level = "low"

    return {
        "risk_level": risk_level,
        "score": total_score,
        "score_percent": _score_percent(total_score, high_threshold),
        "reasons": reasons,
        "findings": [_format_finding(score, reason) for score, reason in sorted(all_findings, reverse=True)],
        "summary": _risk_summary(risk_level, len(all_findings), len(link_warnings)),
        "recommendation": _recommendation(risk_level, has_link_warning=bool(link_warnings)),
        "link_warnings": link_warnings,
    }


def assess_email(msg: dict[str, Any], *, folder: str = "INBOX") -> dict[str, Any]:
    """Rule scoring + (for the uncertain band) a cached, optional AI second opinion."""
    from django.core.cache import cache

    from apps.mail.models import ScamDetectorConfig

    from .llm_classifier import llm_review

    config = ScamDetectorConfig.load()

    if config.is_trusted_sender(msg.get("from_email", "")):
        return _trusted_result()

    result = analyze_email(
        msg,
        brands=config.brand_keywords(),
        medium_threshold=config.medium_threshold,
        high_threshold=config.high_threshold,
    )

    if result["risk_level"] != config.ai_review_band or not config.ai_review_enabled:
        return result

    cache_key = f"scam:llm:{folder}:{msg.get('uid', '')}"
    review = cache.get(cache_key)
    if review is None:
        review = llm_review(msg)
        if review:
            cache.set(cache_key, review, LLM_REVIEW_CACHE_TTL)
    if review:
        _merge_ai_review(result, review)
    return result


def _merge_ai_review(result: dict[str, Any], review: dict[str, Any]) -> None:
    result["ai_review"] = review
    verdict = review.get("verdict")
    confidence = review.get("confidence", 0) or 0
    if verdict == "scam" and confidence >= 0.7:
        result["risk_level"] = "high"
        result["score_percent"] = max(result.get("score_percent", 0), 90)
        for reason in review.get("reasons", []):
            result["reasons"].append(reason)
            result["findings"].append({"category": "AI review", "impact": "High", "score": 0, "reason": reason})
        result["summary"] = "AI review flagged this message as a likely scam. " + result.get("summary", "")
        result["recommendation"] = "Do not act on this message until verified. " + result.get("recommendation", "")
    elif verdict == "legitimate" and confidence >= 0.7:
        result["summary"] = (result.get("summary", "") + " AI review considers this message likely legitimate.").strip()


def _trusted_result() -> dict[str, Any]:
    return {
        "risk_level": "low",
        "score": 0,
        "score_percent": 0,
        "reasons": [],
        "findings": [],
        "summary": "Sender is on the trusted allowlist; automated checks were skipped.",
        "recommendation": "Continue normal handling.",
        "link_warnings": [],
    }


def _score_percent(score: int, high_threshold: int = HIGH_THRESHOLD) -> int:
    if score <= 0:
        return 0
    threshold = high_threshold or HIGH_THRESHOLD
    return min(round((score / threshold) * 100), 100)


def _format_finding(score: int, reason: str) -> dict[str, Any]:
    return {
        "category": _category_for_reason(reason),
        "impact": _impact_label(score),
        "score": score,
        "reason": reason,
    }


def _category_for_reason(reason: str) -> str:
    reason_lower = reason.lower()
    if any(term in reason_lower for term in ("spf", "dkim", "dmarc", "reply-to", "return-path", "authentication")):
        return "Sender authentication"
    if any(term in reason_lower for term in ("link", "url", "ip address", "shortened")):
        return "Link integrity"
    if any(
        term in reason_lower
        for term in ("sender", "display name", "freemail", "email domain", "imitates", "typosquat", "punycode")
    ):
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


__all__ = ["HIGH_THRESHOLD", "MEDIUM_THRESHOLD", "analyze_email", "assess_email"]
