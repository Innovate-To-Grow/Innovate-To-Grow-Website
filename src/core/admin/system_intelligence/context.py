import logging

from django.contrib import admin
from django.template.response import TemplateResponse
from django.urls import reverse

from core.models.base.system_intelligence import SystemIntelligenceConfig
from core.services.system_intelligence_adk.context_window import estimate_context_window
from core.services.system_intelligence_tools import get_adk_tool_metadata

logger = logging.getLogger(__name__)


def _resolve_model_name(model_id):
    """Return a friendly display name for a Bedrock model ID, or the raw ID."""
    if not model_id:
        return "Not configured"
    try:
        from core.services.bedrock import get_available_models

        for _group, models in get_available_models():
            for mid, name in models:
                if mid == model_id:
                    return name
    except Exception:
        logger.exception("Failed to resolve model display name for '%s'.", model_id)
    return model_id


def chat_list_view(request):
    """Render the main AI chat shell page."""
    from core.models import AWSCredentialConfig

    si_config = SystemIntelligenceConfig.load()
    aws_config = AWSCredentialConfig.load()
    model_id = aws_config.default_model_id
    tools = get_adk_tool_metadata()
    si_url = (
        reverse("admin:core_systemintelligenceconfig_change", args=[si_config.pk])
        if si_config.pk
        else reverse("admin:core_systemintelligenceconfig_changelist")
    )
    aws_url = (
        reverse("admin:core_awscredentialconfig_change", args=[aws_config.pk])
        if aws_config.pk
        else reverse("admin:core_awscredentialconfig_changelist")
    )
    context = {
        **admin.site.each_context(request),
        "title": "System Intelligence",
        "si_config": si_config,
        "aws_config": aws_config,
        "model_id": model_id or "",
        "model_name": _resolve_model_name(model_id),
        "context_window": estimate_context_window(model_id),
        "tools": tools,
        "tool_count": len(tools),
        "si_config_url": si_url,
        "aws_config_url": aws_url,
    }
    return TemplateResponse(request, "admin/core/system_intelligence.html", context)
