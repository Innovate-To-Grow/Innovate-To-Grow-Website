from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.template.response import TemplateResponse
from django.urls import reverse

from apps.core.access import user_can_access_app

UUID_PLACEHOLDER = "00000000-0000-0000-0000-000000000000"


def chat_list_view(request):
    """Render the primary System Intelligence chat UI."""
    # admin_view only enforces is_staff; re-check the per-app model here.
    if not user_can_access_app(request.user, "system_intelligence"):
        raise PermissionDenied("You do not have permission to access System Intelligence.")
    context = {
        **admin.site.each_context(request),
        "title": "Chat",
        "chat_config": _chat_config(),
    }
    return TemplateResponse(request, "admin/system_intelligence/system_intelligence_chat.html", context)


def _chat_config():
    return {
        "urls": {
            "conversations": reverse("admin:system_intelligence_conversations"),
            "newConversation": reverse("admin:system_intelligence_new"),
            "detail": reverse("admin:system_intelligence_detail", args=[UUID_PLACEHOLDER]),
            "send": reverse("admin:system_intelligence_send", args=[UUID_PLACEHOLDER]),
            "command": reverse("admin:system_intelligence_command", args=[UUID_PLACEHOLDER]),
            "delete": reverse("admin:system_intelligence_delete", args=[UUID_PLACEHOLDER]),
            "rename": reverse("admin:system_intelligence_rename", args=[UUID_PLACEHOLDER]),
            "approve": reverse("admin:system_intelligence_action_approve", args=[UUID_PLACEHOLDER]),
            "reject": reverse("admin:system_intelligence_action_reject", args=[UUID_PLACEHOLDER]),
            "preview": reverse("admin:system_intelligence_action_preview", args=[UUID_PLACEHOLDER]),
            "fullPreview": reverse("admin:system_intelligence_action_full_preview", args=[UUID_PLACEHOLDER]),
            "exportDownload": reverse("admin:system_intelligence_export_download", args=[UUID_PLACEHOLDER]),
        },
        "uuidPlaceholder": UUID_PLACEHOLDER,
    }
