from django.contrib import admin
from django.urls import path

from .actions import action_approve_view, action_full_preview_view, action_preview_view, action_reject_view
from .commands import chat_command_view
from .context import chat_list_view
from .conversations import chat_delete_view, chat_rename_view, chat_view, conversations_fragment, new_conversation_view
from .stream import chat_send_view


def get_system_intelligence_urls():
    """Return URL patterns for the System Intelligence admin views."""
    return [
        path("core/system-intelligence/", admin.site.admin_view(chat_list_view), name="core_system_intelligence"),
        path(
            "core/system-intelligence/conversations/",
            admin.site.admin_view(conversations_fragment),
            name="core_system_intelligence_conversations",
        ),
        path(
            "core/system-intelligence/new/",
            admin.site.admin_view(new_conversation_view),
            name="core_system_intelligence_new",
        ),
        path(
            "core/system-intelligence/<uuid:conversation_id>/",
            admin.site.admin_view(chat_view),
            name="core_system_intelligence_detail",
        ),
        path(
            "core/system-intelligence/<uuid:conversation_id>/send/",
            admin.site.admin_view(chat_send_view),
            name="core_system_intelligence_send",
        ),
        path(
            "core/system-intelligence/<uuid:conversation_id>/command/",
            admin.site.admin_view(chat_command_view),
            name="core_system_intelligence_command",
        ),
        path(
            "core/system-intelligence/<uuid:conversation_id>/delete/",
            admin.site.admin_view(chat_delete_view),
            name="core_system_intelligence_delete",
        ),
        path(
            "core/system-intelligence/<uuid:conversation_id>/rename/",
            admin.site.admin_view(chat_rename_view),
            name="core_system_intelligence_rename",
        ),
        path(
            "core/system-intelligence/actions/<uuid:action_id>/approve/",
            admin.site.admin_view(action_approve_view),
            name="core_system_intelligence_action_approve",
        ),
        path(
            "core/system-intelligence/actions/<uuid:action_id>/reject/",
            admin.site.admin_view(action_reject_view),
            name="core_system_intelligence_action_reject",
        ),
        path(
            "core/system-intelligence/actions/<uuid:action_id>/preview/",
            admin.site.admin_view(action_preview_view),
            name="core_system_intelligence_action_preview",
        ),
        path(
            "core/system-intelligence/actions/<uuid:action_id>/preview/full/",
            admin.site.admin_view(action_full_preview_view),
            name="core_system_intelligence_action_full_preview",
        ),
    ]
