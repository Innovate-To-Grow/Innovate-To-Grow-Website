from django.contrib import admin
from django.template.response import TemplateResponse

from system_intelligence.admin.adk_web import SYSTEM_INTELLIGENCE_ADK_DEV_UI_PATH


def chat_list_view(request):
    """Render the official ADK Web shell wrapper."""
    context = {
        **admin.site.each_context(request),
        "title": "System Intelligence",
        "adk_web_url": SYSTEM_INTELLIGENCE_ADK_DEV_UI_PATH,
    }
    return TemplateResponse(request, "admin/system_intelligence/system_intelligence_adk.html", context)
