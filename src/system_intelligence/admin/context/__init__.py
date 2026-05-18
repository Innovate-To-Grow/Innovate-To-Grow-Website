from django.contrib import admin
from django.template.response import TemplateResponse
from django.urls import reverse

from system_intelligence.admin.adk_web import SYSTEM_INTELLIGENCE_ADK_DEV_UI_PATH

UUID_PLACEHOLDER = "00000000-0000-0000-0000-000000000000"


def chat_list_view(request):
    """Render the primary System Intelligence chat UI."""
    context = {
        **admin.site.each_context(request),
        "title": "System Intelligence",
        "chat_config": _chat_config(),
    }
    return TemplateResponse(request, "admin/system_intelligence/system_intelligence_chat.html", context)


def debug_view(request):
    """Render the official ADK Web shell wrapper for debugging."""
    context = {
        **admin.site.each_context(request),
        "title": "System Intelligence Debug",
        "adk_web_url": SYSTEM_INTELLIGENCE_ADK_DEV_UI_PATH,
    }
    return TemplateResponse(request, "admin/system_intelligence/system_intelligence_adk.html", context)


def _chat_config():
    return {
        "urls": {
            "conversations": reverse("admin:system_intelligence_conversations"),
            "newConversation": reverse("admin:system_intelligence_new"),
            "debug": reverse("admin:system_intelligence_debug"),
            "detail": reverse("admin:system_intelligence_detail", args=[UUID_PLACEHOLDER]),
            "send": reverse("admin:system_intelligence_send", args=[UUID_PLACEHOLDER]),
            "command": reverse("admin:system_intelligence_command", args=[UUID_PLACEHOLDER]),
            "delete": reverse("admin:system_intelligence_delete", args=[UUID_PLACEHOLDER]),
            "rename": reverse("admin:system_intelligence_rename", args=[UUID_PLACEHOLDER]),
            "approve": reverse("admin:system_intelligence_action_approve", args=[UUID_PLACEHOLDER]),
            "reject": reverse("admin:system_intelligence_action_reject", args=[UUID_PLACEHOLDER]),
            "preview": reverse("admin:system_intelligence_action_preview", args=[UUID_PLACEHOLDER]),
            "fullPreview": reverse("admin:system_intelligence_action_full_preview", args=[UUID_PLACEHOLDER]),
        },
        "uuidPlaceholder": UUID_PLACEHOLDER,
    }
