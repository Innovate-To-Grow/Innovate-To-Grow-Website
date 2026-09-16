"""Editor context construction."""

from django.conf import settings as django_settings
from django.core.serializers.json import DjangoJSONEncoder
from django.urls import reverse

from apps.cms.app_routes import widget_supports_schedule
from apps.cms.models import (
    BLOCK_SCHEMAS,
    BLOCK_TYPE_CHOICES,
    CMSEmbedAllowedHost,
    CMSEmbedWidget,
)
from apps.cms.models.content.cms.block_types import DEFAULT_SANDBOX
from apps.cms.models.media import ALLOWED_ASSET_EXTENSIONS, IMAGE_ASSET_EXTENSIONS, MAX_ASSET_UPLOAD_BYTES
from apps.cms.services.embed.embed_sections import hidden_section_presets_payload
from apps.event.models import CurrentProjectSchedule

from .json_utils import _safe_json


def _format_widget_label(widget):
    parts = [widget.slug]
    if widget.admin_label:
        parts.append(widget.admin_label)
    if widget.widget_type == "app_route" and widget.app_route:
        parts.append(f"app route: {widget.app_route}")
    elif widget.page_id and widget.page:
        parts.append(f"page: {widget.page.title}")
    return " - ".join(parts)


def _schedule_choices():
    """Schedules an ``embed_widget`` block may pin (active first, then newest)."""
    return [
        {"id": str(schedule.pk), "name": str(schedule), "is_active": schedule.is_active}
        for schedule in CurrentProjectSchedule.objects.order_by("-is_active", "-created_at")
    ]


def build_editor_context(obj=None):
    allowed_hosts = list(
        CMSEmbedAllowedHost.objects.filter(is_active=True).order_by("hostname").values_list("hostname", flat=True)
    )
    embed_widgets = [
        {
            "slug": widget.slug,
            "label": _format_widget_label(widget),
            "widget_type": widget.widget_type,
            "app_route": widget.app_route or "",
            # Whether the block editor offers the Schedule dropdown, and the
            # widget-level default it shows there (a CMS_SCHEDULES id).
            "supports_schedule": widget_supports_schedule(widget),
            "schedule_id": str(widget.schedule_id) if widget_supports_schedule(widget) and widget.schedule_id else "",
        }
        for widget in CMSEmbedWidget.objects.select_related("page").order_by("slug")
    ]
    context = {
        "block_schemas_json": _safe_json(BLOCK_SCHEMAS),
        "block_type_choices_json": _safe_json(BLOCK_TYPE_CHOICES),
        "embed_allowed_hosts_json": _safe_json(allowed_hosts),
        "embed_widgets_json": _safe_json(embed_widgets),
        "schedules_json": _safe_json(_schedule_choices()),
        "hidden_section_presets_json": _safe_json(hidden_section_presets_payload()),
        "asset_manager_config_json": _safe_json(_asset_manager_config()),
        "embed_default_sandbox": DEFAULT_SANDBOX,
        "route_check_url": reverse("admin:cms_cmspage_route_conflict"),
        "current_page_id": str(obj.pk) if obj else "",
        "current_page_route": obj.route if obj else "",
        "frontend_url": (getattr(django_settings, "FRONTEND_URL", "") or "").rstrip("/"),
    }
    if not obj:
        context["initial_blocks_json"] = "[]"
        return context

    blocks = obj.blocks.all().order_by("sort_order")
    context["initial_blocks_json"] = _safe_json(
        [
            {
                "block_type": block.block_type,
                "sort_order": block.sort_order,
                "admin_label": block.admin_label,
                "data": block.data,
            }
            for block in blocks
        ],
        cls=DjangoJSONEncoder,
    )
    return context


def _asset_manager_config():
    return {
        "listUrl": reverse("admin:cms_cmspage_assets"),
        "uploadUrl": reverse("admin:cms_cmspage_asset_upload"),
        "allowedExtensions": ALLOWED_ASSET_EXTENSIONS,
        "imageExtensions": IMAGE_ASSET_EXTENSIONS,
        "maxBytes": MAX_ASSET_UPLOAD_BYTES,
    }
