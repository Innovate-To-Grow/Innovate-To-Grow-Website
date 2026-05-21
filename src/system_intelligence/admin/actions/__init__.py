"""System Intelligence action admin views."""

# ruff: noqa: E402

import logging

from system_intelligence.services import actions as system_intelligence_actions

logger = logging.getLogger(__name__)

GENERIC_ACTION_ERROR = "Could not process this action request."
GENERIC_PERMISSION_ERROR = "Action request not found."
GENERIC_VALIDATION_ERROR = "Validation failed for the proposed change."

from .lookup import _changed_preview_blocks, _cms_preview_page, _get_user_action_request
from .rendering import (
    _heading_level,
    _link_label,
    _render_block_body,
    _render_faq_list,
    _render_heading_and_html,
    _render_link_list,
    _render_preview_block,
    _render_preview_blocks,
    _render_section_group,
    _render_table,
    _safe_href,
)
from .views import action_approve_view, action_full_preview_view, action_preview_view, action_reject_view

__all__ = [
    "_changed_preview_blocks",
    "_cms_preview_page",
    "_get_user_action_request",
    "_render_preview_blocks",
    "action_approve_view",
    "action_full_preview_view",
    "action_preview_view",
    "action_reject_view",
    "system_intelligence_actions",
]
