from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse

from core.models.base.system_intelligence import SystemIntelligenceActionRequest
from core.services import system_intelligence_actions


def action_approve_view(request, action_id):
    """Approve and apply a pending System Intelligence action request."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    try:
        action = _get_user_action_request(request, action_id)
    except PermissionDenied as exc:
        return JsonResponse({"error": str(exc)}, status=404)
    try:
        action = system_intelligence_actions.approve_action_request(action.id, request.user)
    except (PermissionDenied, system_intelligence_actions.ActionRequestError, ValidationError, ValueError) as exc:
        action.refresh_from_db()
        return JsonResponse(
            {"error": str(exc), "action_request": system_intelligence_actions.serialize_action_request(action)},
            status=400,
        )
    return JsonResponse({"ok": True, "action_request": system_intelligence_actions.serialize_action_request(action)})


def action_reject_view(request, action_id):
    """Reject a pending System Intelligence action request."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    try:
        action = _get_user_action_request(request, action_id)
    except PermissionDenied as exc:
        return JsonResponse({"error": str(exc)}, status=404)
    try:
        action = system_intelligence_actions.reject_action_request(action.id, request.user)
    except system_intelligence_actions.ActionRequestError as exc:
        return JsonResponse(
            {"error": str(exc), "action_request": system_intelligence_actions.serialize_action_request(action)},
            status=400,
        )
    return JsonResponse({"ok": True, "action_request": system_intelligence_actions.serialize_action_request(action)})


def _get_user_action_request(request, action_id):
    try:
        return SystemIntelligenceActionRequest.objects.get(id=action_id, conversation__created_by=request.user)
    except SystemIntelligenceActionRequest.DoesNotExist:
        raise PermissionDenied("Action request not found.")
