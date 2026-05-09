from typing import Any

from core.models.base.system_intelligence import SystemIntelligenceActionRequest

from ..comparison import action_comparison

_FAILURE_NOTICE_BY_STATUS: dict[str, str] = {
    SystemIntelligenceActionRequest.STATUS_FAILED: (
        "This action could not be applied. Try proposing it again or contact an admin."
    ),
}


def serialize_action_request(action: SystemIntelligenceActionRequest) -> dict[str, Any]:
    """Return the stable JSON payload used by SSE and the admin chat UI.

    The raw ``error_message`` field is intentionally excluded; only a
    status-derived notice is returned. This keeps any exception text the
    backend persisted on failure out of the public response and confines
    failure detail to the admin model view + server logs.
    """
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
        "failure_notice": _FAILURE_NOTICE_BY_STATUS.get(action.status, ""),
    }


def proposal_tool_response(action: SystemIntelligenceActionRequest, result: str) -> dict[str, Any]:
    return {"result": result, "action_request": serialize_action_request(action)}
