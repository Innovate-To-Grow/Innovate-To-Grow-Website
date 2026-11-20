"""Lookup and diff helpers for System Intelligence action requests."""

from django.core.cache import cache
from django.core.exceptions import PermissionDenied

from apps.core.utils.access import user_can_access_app
from apps.system_intelligence.models import SystemIntelligenceActionRequest
from apps.system_intelligence.services.actions.comparison import block_key
from apps.system_intelligence.services.actions.engine.tool_access import has_chat_grants


def _get_user_action_request(request, action_id):
    try:
        action = SystemIntelligenceActionRequest.objects.select_related("conversation").get(
            id=action_id, conversation__created_by=request.user
        )
    except SystemIntelligenceActionRequest.DoesNotExist:
        raise PermissionDenied("Action request not found.")
    if not user_can_access_app(request.user, action.target_app_label) or not has_chat_grants(
        request.user, action.conversation.required_tool_apps
    ):
        raise PermissionDenied("Action request not found.")
    return action


def _cms_preview_page(action):
    if action.action_type != SystemIntelligenceActionRequest.ACTION_CMS_PAGE_UPDATE:
        return None
    cached = cache.get(f"cms:preview:{action.preview_token}") if action.preview_token else None
    if isinstance(cached, dict):
        return cached
    payload = action.payload if isinstance(action.payload, dict) else {}
    page = payload.get("page")
    return page if isinstance(page, dict) else None


def _changed_preview_blocks(action, page):
    after_blocks = page.get("blocks") if isinstance(page.get("blocks"), list) else []
    before = action.before_snapshot if isinstance(action.before_snapshot, dict) else {}
    before_blocks = before.get("blocks") if isinstance(before.get("blocks"), list) else []
    before_map = {
        block_key(block, index): block for index, block in enumerate(before_blocks) if isinstance(block, dict)
    }
    changed_blocks = []
    for index, block in enumerate(after_blocks):
        if not isinstance(block, dict):
            continue
        key = block_key(block, index)
        if before_map.get(key) != block:
            changed_blocks.append(block)
    return changed_blocks
