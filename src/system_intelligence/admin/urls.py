from django.contrib import admin
from django.urls import path

from .actions import action_approve_view, action_full_preview_view, action_preview_view, action_reject_view
from .commands import chat_command_view
from .context import chat_list_view
from .conversations import chat_delete_view, chat_rename_view, chat_view, conversations_fragment, new_conversation_view
from .exports import export_download_view
from .stream import chat_send_view


def get_system_intelligence_urls():
    """Return URL patterns for the System Intelligence admin views."""
    return [
        path("system-intelligence/", admin.site.admin_view(chat_list_view), name="system_intelligence"),
        path(
            "system-intelligence/conversations/",
            admin.site.admin_view(conversations_fragment),
            name="system_intelligence_conversations",
        ),
        path(
            "system-intelligence/new/",
            admin.site.admin_view(new_conversation_view),
            name="system_intelligence_new",
        ),
        path(
            "system-intelligence/<uuid:conversation_id>/",
            admin.site.admin_view(chat_view),
            name="system_intelligence_detail",
        ),
        path(
            "system-intelligence/<uuid:conversation_id>/send/",
            admin.site.admin_view(chat_send_view),
            name="system_intelligence_send",
        ),
        path(
            "system-intelligence/<uuid:conversation_id>/command/",
            admin.site.admin_view(chat_command_view),
            name="system_intelligence_command",
        ),
        path(
            "system-intelligence/<uuid:conversation_id>/delete/",
            admin.site.admin_view(chat_delete_view),
            name="system_intelligence_delete",
        ),
        path(
            "system-intelligence/<uuid:conversation_id>/rename/",
            admin.site.admin_view(chat_rename_view),
            name="system_intelligence_rename",
        ),
        path(
            "system-intelligence/actions/<uuid:action_id>/approve/",
            admin.site.admin_view(action_approve_view),
            name="system_intelligence_action_approve",
        ),
        path(
            "system-intelligence/actions/<uuid:action_id>/reject/",
            admin.site.admin_view(action_reject_view),
            name="system_intelligence_action_reject",
        ),
        path(
            "system-intelligence/actions/<uuid:action_id>/preview/",
            admin.site.admin_view(action_preview_view),
            name="system_intelligence_action_preview",
        ),
        path(
            "system-intelligence/actions/<uuid:action_id>/preview/full/",
            admin.site.admin_view(action_full_preview_view),
            name="system_intelligence_action_full_preview",
        ),
        path(
            "system-intelligence/exports/<uuid:export_id>/download/",
            admin.site.admin_view(export_download_view),
            name="system_intelligence_export_download",
        ),
    ]
