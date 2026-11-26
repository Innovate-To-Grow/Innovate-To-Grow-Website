"""The System Intelligence configuration admin (Assistant Settings): models, prompts, budgets, and which row is
active. The change form's tabs are in ``config_fieldsets``."""

import logging

from django.contrib import admin, messages
from django.contrib.admin.utils import unquote
from django.db import IntegrityError
from django.http import Http404, HttpResponseNotAllowed, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.html import format_html, format_html_join
from django.views.decorators.csrf import csrf_protect
from unfold.decorators import action, display

from apps.core.admin.common.base import BaseModelAdmin
from apps.system_intelligence.models import SystemIntelligenceConfig
from apps.system_intelligence.services.public_assistant import global_budget_usage

from .config_fieldsets import CONFIG_FIELDSETS
from .forms import SystemIntelligenceConfigForm

logger = logging.getLogger(__name__)


@admin.register(SystemIntelligenceConfig)
class SystemIntelligenceConfigAdmin(BaseModelAdmin):
    form = SystemIntelligenceConfigForm
    list_display = (
        "name",
        "status_badge",
        "default_model_display",
        "public_assistant_enabled",
        "temperature",
        "max_tokens",
        "updated_at",
    )
    list_filter = ("is_active", "public_assistant_enabled")
    search_fields = ("name",)
    list_select_related = ("default_provider",)
    ordering = ("-is_active", "-updated_at")
    actions_detail = ["activate_this_config"]
    fieldsets = CONFIG_FIELDSETS
    readonly_fields = ("id", "created_at", "updated_at", "public_assistant_global_usage")

    @display(description="Status", label={"active": "success", "inactive": "danger"})
    def status_badge(self, obj):
        return ("active", "Active") if obj.is_active else ("inactive", "Inactive")

    @display(description="Global Tokens Used (current window)")
    def public_assistant_global_usage(self, obj):
        """Read-only: how close each feature's global budget is to the limit above.

        The counters are site-wide (one per feature), not per config, and are
        read without locking anything.
        """
        try:
            usage = global_budget_usage()
        except Exception:
            logger.exception("Could not read the assistant global token budget usage.")
            return "Usage is unavailable right now (the budget store could not be read)."
        limit = obj.public_assistant_global_token_limit or 0
        rows = []
        for entry in usage:
            if limit > 0:
                spent = f"{entry.tokens_used:,} of {limit:,} tokens ({entry.tokens_used * 100 // limit}%)"
            else:
                spent = f"{entry.tokens_used:,} tokens; switched off (the limit is 0)"
            if entry.window_expires_at is not None:
                window = f"window ends {timezone.localtime(entry.window_expires_at):%Y-%m-%d %H:%M %Z}"
            elif entry.tokens_used:
                window = "window open"
            else:
                window = "no window open"
            rows.append((entry.label, spent, window))
        note = (
            "Each feature has its own counter. Reserved tokens of calls in flight are included."
            if obj.is_active
            else "Each feature has its own counter. This config is not active: the counters are site-wide and "
            "the active config's limit is the one enforced."
        )
        return format_html(
            "{}<div>{}</div>",
            format_html_join("", "<div><strong>{}:</strong> {} &middot; {}</div>", rows),
            note,
        )

    @display(description="Default Model")
    def default_model_display(self, obj):
        if not obj.default_model_id:
            return "—"
        if obj.default_provider_id:
            return f"{obj.default_provider.name} · {obj.default_model_id}"
        try:
            from apps.system_intelligence.services.bedrock import get_available_models

            match = next(
                (
                    name
                    for _group, models in get_available_models()
                    for mid, name in models
                    if mid == obj.default_model_id
                ),
                None,
            )
            if match is not None:
                return match
        except Exception:
            logger.exception(
                "Failed to resolve default model display name for System Intelligence config '%s'.", obj.pk
            )
        return obj.default_model_id

    @action(description="Activate this config", url_path="activate", icon="check_circle", permissions=["change"])
    @method_decorator(csrf_protect)
    def activate_this_config(self, request, object_id):
        if request.method not in {"GET", "POST"}:
            return HttpResponseNotAllowed(["GET", "POST"])
        obj = self.get_object(request, unquote(str(object_id)))
        if obj is None:
            raise Http404("Configuration not found.")
        change_url = reverse("admin:system_intelligence_systemintelligenceconfig_change", args=[obj.pk])
        if request.method == "GET":
            return TemplateResponse(
                request,
                "admin/system_intelligence/confirm_activation.html",
                {
                    **self.admin_site.each_context(request),
                    "title": "Activate System Intelligence configuration",
                    "configuration": obj,
                    "change_url": change_url,
                },
            )
        obj.is_active = True
        try:
            obj.save(update_fields=["is_active", "updated_at"])
        except IntegrityError:
            messages.error(request, "Another configuration was activated at the same time. Try again.")
            return HttpResponseRedirect(change_url)
        messages.success(request, f'"{obj.name}" is now the active System Intelligence config.')
        return HttpResponseRedirect(change_url)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_active:
            return False
        return super().has_delete_permission(request, obj)

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions
