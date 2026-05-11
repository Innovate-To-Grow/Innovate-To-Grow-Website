"""Approve, reject, and preview System Intelligence action requests."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, JsonResponse
from django.template.response import TemplateResponse
from django.views.decorators.clickjacking import xframe_options_sameorigin

import core.admin.system_intelligence.actions as actions_api
from core.models.base.system_intelligence import SystemIntelligenceActionRequest

from .lookup import _changed_preview_blocks, _cms_preview_page, _get_user_action_request
from .rendering import _render_preview_blocks


def action_approve_view(request, action_id):
    """Approve and apply a pending System Intelligence action request."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    try:
        action = _get_user_action_request(request, action_id)
    except PermissionDenied:
        return JsonResponse({"error": actions_api.GENERIC_PERMISSION_ERROR}, status=404)
    try:
        action = actions_api.system_intelligence_actions.approve_action_request(action.id, request.user)
    except (
        PermissionDenied,
        actions_api.system_intelligence_actions.ActionRequestError,
        ValidationError,
        ValueError,
    ) as exc:
        action.refresh_from_db()
        return _action_error_response(exc, action=action)
    return JsonResponse(
        {"ok": True, "action_request": actions_api.system_intelligence_actions.serialize_action_request(action)}
    )


def action_reject_view(request, action_id):
    """Reject a pending System Intelligence action request."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    try:
        action = _get_user_action_request(request, action_id)
    except PermissionDenied:
        return JsonResponse({"error": actions_api.GENERIC_PERMISSION_ERROR}, status=404)
    try:
        action = actions_api.system_intelligence_actions.reject_action_request(action.id, request.user)
    except actions_api.system_intelligence_actions.ActionRequestError as exc:
        return _action_error_response(exc, action=action)
    return JsonResponse(
        {"ok": True, "action_request": actions_api.system_intelligence_actions.serialize_action_request(action)}
    )


def _action_error_response(exc, *, action):
    """Build a JsonResponse using a class-derived literal and log full detail."""
    action_id = getattr(action, "id", None)
    if isinstance(exc, actions_api.system_intelligence_actions.ActionRequestError):
        actions_api.logger.warning("Action %s rejected by validation", action_id, exc_info=exc)
        message = actions_api.GENERIC_ACTION_ERROR
    elif isinstance(exc, PermissionDenied):
        message = actions_api.GENERIC_PERMISSION_ERROR
    elif isinstance(exc, ValidationError):
        actions_api.logger.warning("Action %s validation error", action_id, exc_info=exc)
        message = actions_api.GENERIC_VALIDATION_ERROR
    else:
        actions_api.logger.exception("Unexpected error handling action %s", action_id)
        message = actions_api.GENERIC_ACTION_ERROR
    return JsonResponse(
        {"error": message, "action_request": actions_api.system_intelligence_actions.serialize_action_request(action)},
        status=400,
    )


@xframe_options_sameorigin
def action_preview_view(request, action_id):
    """Render a same-origin iframe preview for a pending CMS page action."""
    try:
        action = _get_user_action_request(request, action_id)
    except PermissionDenied as exc:
        raise Http404(str(exc)) from exc

    payload = action.payload if isinstance(action.payload, dict) else {}
    page = payload.get("page")
    if action.action_type != SystemIntelligenceActionRequest.ACTION_CMS_PAGE_UPDATE or not isinstance(page, dict):
        raise Http404("Preview not available.")

    preview_blocks = _changed_preview_blocks(action, page)
    return _preview_response(
        request,
        action,
        page,
        preview_blocks,
        "Previewing changed CMS block content. This change is not applied until approved.",
        "No CMS block content changed in this proposal.",
    )


@xframe_options_sameorigin
def action_full_preview_view(request, action_id):
    """Render the full proposed CMS page in a new admin preview tab."""
    try:
        action = _get_user_action_request(request, action_id)
    except PermissionDenied as exc:
        raise Http404(str(exc)) from exc

    page = _cms_preview_page(action)
    if page is None:
        raise Http404("Preview not available.")

    blocks = page.get("blocks") if isinstance(page.get("blocks"), list) else []
    return _preview_response(
        request,
        action,
        page,
        blocks,
        "Previewing full proposed CMS page content. This change is not applied until approved.",
        "This proposed CMS page has no block content to preview.",
    )


def _preview_response(request, action, page, blocks, banner_text, empty_text):
    return TemplateResponse(
        request,
        "admin/core/system_intelligence_action_preview.html",
        {
            "action": action,
            "page": page,
            "block_html": _render_preview_blocks(blocks),
            "has_changed_blocks": bool(blocks),
            "has_preview_blocks": bool(blocks),
            "banner_text": banner_text,
            "empty_text": empty_text,
        },
    )
