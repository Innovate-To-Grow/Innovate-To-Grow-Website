from typing import Any

from core.models.base.system_intelligence import SystemIntelligenceActionRequest

from .comparison import action_comparison


def serialize_action_request(action: SystemIntelligenceActionRequest) -> dict[str, Any]:
    """Return the stable JSON payload used by SSE and the admin chat UI."""
    payload = action.payload if isinstance(action.payload, dict) else {}
    return {
        "id": str(action.id),
        "status": action.status,
        "action_type": action.action_type,
        "title": action.title,
        "summary": action.summary,
        "target": {
            "app_label": action.target_app_label,
            "model": action.target_model,
            "pk": action.target_pk,
            "repr": action.target_repr,
        },
        "diff": action.diff or [],
        "comparison": action_comparison(action, payload),
        "preview_url": action.preview_url,
        "created_at": action.created_at.isoformat() if action.created_at else "",
        "reviewed_at": action.reviewed_at.isoformat() if action.reviewed_at else "",
        "applied_at": action.applied_at.isoformat() if action.applied_at else "",
        "error_message": action.error_message,
    }


def proposal_tool_response(action: SystemIntelligenceActionRequest, result: str) -> dict[str, Any]:
    return {"result": result, "action_request": serialize_action_request(action)}
