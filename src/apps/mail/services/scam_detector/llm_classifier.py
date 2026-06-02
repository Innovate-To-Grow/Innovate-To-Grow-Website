"""Optional AI second opinion for borderline scam emails (Amazon Bedrock / Claude).

Reuses the project's Bedrock client. Designed to be best-effort: any failure
(unconfigured AWS, disabled flag, API error, unparseable output) returns ``None``
so the caller falls back to the deterministic rule result. Never raises.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from apps.core.models import AWSCredentialConfig
from apps.core.services.bedrock import invoke_bedrock
from apps.mail.models import ScamDetectorConfig
from apps.system_intelligence.models import SystemIntelligenceConfig

logger = logging.getLogger(__name__)

_MAX_BODY_CHARS = 4000
_VERDICTS = {"scam", "suspicious", "legitimate"}
_SYSTEM_PROMPT = (
    "You are an email security analyst classifying whether an email is a "
    "phishing or scam attempt. Respond with ONLY a single JSON object and no "
    "other text, no markdown fences, and do not call any tools. Schema: "
    '{"verdict": "scam" | "suspicious" | "legitimate", '
    '"confidence": number from 0 to 1, "risk_score": integer 0-100, '
    '"reasons": array of short strings}.'
)


def llm_review(msg: dict[str, Any]) -> dict[str, Any] | None:
    """Return a normalized AI verdict dict, or None to fall back to the rules."""
    if not ScamDetectorConfig.load().ai_review_enabled:
        return None
    if not AWSCredentialConfig.load().is_configured:
        return None

    try:
        text = _call_bedrock(_build_prompt(msg))
    except Exception:
        logger.warning("Scam AI review call failed; falling back to rule result.", exc_info=True)
        return None

    data = _parse_json(text)
    if data is None:
        logger.warning("Scam AI review returned unparseable output; falling back to rule result.")
        return None
    return _normalize(data)


def _build_prompt(msg: dict[str, Any]) -> str:
    body = (msg.get("text") or msg.get("html") or "")[:_MAX_BODY_CHARS]
    return (
        f"From: {msg.get('from_name', '')} <{msg.get('from_email', '')}>\n"
        f"Reply-To: {msg.get('reply_to', '')}\n"
        f"Subject: {msg.get('subject', '')}\n"
        f"Authentication-Results: {msg.get('authentication_results', '')}\n\n"
        f"Body:\n{body}"
    )


def _call_bedrock(prompt: str) -> str:
    base = SystemIntelligenceConfig.load()
    chat_config = SystemIntelligenceConfig(
        default_model_id=base.default_model_id,
        system_prompt=_SYSTEM_PROMPT,
        max_tokens=512,
        temperature=0.0,
    )
    response = invoke_bedrock(
        [{"role": "user", "content": prompt}],
        chat_config=chat_config,
        aws_config=AWSCredentialConfig.load(),
    )
    return response.get("text", "") if isinstance(response, dict) else ""


def _parse_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _normalize(data: dict[str, Any]) -> dict[str, Any]:
    verdict = str(data.get("verdict", "")).strip().lower()
    if verdict not in _VERDICTS:
        verdict = "suspicious"
    try:
        confidence = max(0.0, min(1.0, float(data.get("confidence", 0))))
    except (TypeError, ValueError):
        confidence = 0.0
    try:
        risk_score = max(0, min(100, int(data.get("risk_score", 0))))
    except (TypeError, ValueError):
        risk_score = 0
    reasons = [str(reason).strip() for reason in (data.get("reasons") or []) if str(reason).strip()][:6]
    return {"verdict": verdict, "confidence": confidence, "risk_score": risk_score, "reasons": reasons}
