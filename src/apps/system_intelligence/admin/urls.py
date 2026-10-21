from django.contrib import admin
from django.urls import path

from .actions import action_approve_view, action_full_preview_view, action_preview_view, action_reject_view
from .commands import chat_command_view
from .context import chat_list_view
from .conversations import chat_delete_view, chat_rename_view, chat_view, conversations_fragment, new_conversation_view
from .dashboard import usage_dashboard_data_view, usage_dashboard_view
from .exports import export_download_view
from .stream import chat_send_view

# (path, view, URL name), in match order.
_ROUTES = (
    ("system-intelligence/", chat_list_view, "system_intelligence"),
    ("system-intelligence/conversations/", conversations_fragment, "system_intelligence_conversations"),
    ("system-intelligence/new/", new_conversation_view, "system_intelligence_new"),
    # Registered before the "<uuid:conversation_id>/" catch-all below: "usage"
    # is not a UUID so it could never match that converter, but keep static
    # segments ahead of the dynamic one for clear, predictable ordering.
    ("system-intelligence/usage/", usage_dashboard_view, "system_intelligence_usage_dashboard"),
    ("system-intelligence/usage/data/", usage_dashboard_data_view, "system_intelligence_usage_data"),
    ("system-intelligence/<uuid:conversation_id>/", chat_view, "system_intelligence_detail"),
    ("system-intelligence/<uuid:conversation_id>/send/", chat_send_view, "system_intelligence_send"),
    ("system-intelligence/<uuid:conversation_id>/command/", chat_command_view, "system_intelligence_command"),
    ("system-intelligence/<uuid:conversation_id>/delete/", chat_delete_view, "system_intelligence_delete"),
    ("system-intelligence/<uuid:conversation_id>/rename/", chat_rename_view, "system_intelligence_rename"),
    (
        "system-intelligence/actions/<uuid:action_id>/approve/",
        action_approve_view,
        "system_intelligence_action_approve",
    ),
    ("system-intelligence/actions/<uuid:action_id>/reject/", action_reject_view, "system_intelligence_action_reject"),
    (
        "system-intelligence/actions/<uuid:action_id>/preview/",
        action_preview_view,
        "system_intelligence_action_preview",
    ),
    (
        "system-intelligence/actions/<uuid:action_id>/preview/full/",
        action_full_preview_view,
        "system_intelligence_action_full_preview",
    ),
    (
        "system-intelligence/exports/<uuid:export_id>/download/",
        export_download_view,
        "system_intelligence_export_download",
    ),
)


def get_system_intelligence_urls():
    """Return URL patterns for the System Intelligence admin views."""
    return [path(route, admin.site.admin_view(view), name=name) for route, view, name in _ROUTES]
