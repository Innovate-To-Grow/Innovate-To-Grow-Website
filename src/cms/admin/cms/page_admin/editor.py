import json
import os
import uuid
from datetime import timedelta

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone

from cms.embed_sections import hidden_section_presets_payload
from cms.models import (
    BLOCK_SCHEMAS,
    BLOCK_TYPE_CHOICES,
    CMSAsset,
    CMSBlock,
    CMSEmbedAllowedHost,
    CMSEmbedWidget,
    CMSPage,
    validate_block_data,
)
from cms.models.content.cms.block_types import DEFAULT_SANDBOX
from cms.models.content.cms.cms_page import normalize_cms_route, validate_cms_route
from cms.models.media import (
    ALLOWED_ASSET_EXTENSIONS,
    IMAGE_ASSET_EXTENSIONS,
    MAX_ASSET_UPLOAD_BYTES,
)

# Mirrors Django's django.utils.html.json_script escape table so json.dumps
# output is safe to inline inside a <script> block (notably </script>).
_JSON_SCRIPT_ESCAPES = {
    ord("<"): "\\u003C",
    ord(">"): "\\u003E",
    ord("&"): "\\u0026",
    0x2028: "\\u2028",
    0x2029: "\\u2029",
}


def _safe_json(value, **kwargs):
    return json.dumps(value, **kwargs).translate(_JSON_SCRIPT_ESCAPES)


def _format_widget_label(widget):
    parts = [widget.slug]
    if widget.admin_label:
        parts.append(widget.admin_label)
    if widget.widget_type == "app_route" and widget.app_route:
        parts.append(f"app route: {widget.app_route}")
    elif widget.page_id and widget.page:
        parts.append(f"page: {widget.page.title}")
    return " — ".join(parts)


def _asset_extension(asset):
    _, ext = os.path.splitext(asset.file.name if asset.file else "")
    return ext.lstrip(".").lower()


def _validation_error_payload(exc):
    if hasattr(exc, "message_dict"):
        errors = exc.message_dict
        messages = [message for field_errors in errors.values() for message in field_errors]
        return {"detail": messages[0] if messages else "Validation error.", "errors": errors}
    messages = getattr(exc, "messages", None) or [str(exc)]
    return {"detail": messages[0], "errors": messages}


def serialize_asset(asset):
    extension = _asset_extension(asset)
    try:
        size = asset.file.size if asset.file else None
    except (OSError, ValueError):
        size = None
    return {
        "id": str(asset.pk),
        "name": asset.name,
        "file": asset.file.name if asset.file else "",
        "public_url": asset.public_url,
        "url": asset.public_url,
        "extension": extension,
        "is_image": extension in IMAGE_ASSET_EXTENSIONS,
        "size": size,
        "updated_at": asset.updated_at.isoformat() if asset.updated_at else "",
    }


def build_editor_context(obj=None):
    from django.conf import settings as django_settings

    allowed_hosts = list(
        CMSEmbedAllowedHost.objects.filter(is_active=True).order_by("hostname").values_list("hostname", flat=True)
    )
    embed_widgets = [
        {
            "slug": widget.slug,
            "label": _format_widget_label(widget),
            "widget_type": widget.widget_type,
            "app_route": widget.app_route or "",
        }
        for widget in CMSEmbedWidget.objects.order_by("slug")
    ]
    context = {
        "block_schemas_json": _safe_json(BLOCK_SCHEMAS),
        "block_type_choices_json": _safe_json(BLOCK_TYPE_CHOICES),
        "embed_allowed_hosts_json": _safe_json(allowed_hosts),
        "embed_widgets_json": _safe_json(embed_widgets),
        "hidden_section_presets_json": _safe_json(hidden_section_presets_payload()),
        "asset_manager_config_json": _safe_json(
            {
                "listUrl": reverse("admin:cms_cmspage_assets"),
                "uploadUrl": reverse("admin:cms_cmspage_asset_upload"),
                "allowedExtensions": ALLOWED_ASSET_EXTENSIONS,
                "imageExtensions": IMAGE_ASSET_EXTENSIONS,
                "maxBytes": MAX_ASSET_UPLOAD_BYTES,
            }
        ),
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


def save_blocks_from_json(request, page, messages):
    blocks_json = request.POST.get("blocks_json", "")
    if not blocks_json:
        return
    try:
        blocks_data = json.loads(blocks_json)
        if not isinstance(blocks_data, list):
            messages.error(request, "Invalid blocks data: expected a JSON array.")
            return
    except json.JSONDecodeError as exc:
        messages.error(request, f"Invalid blocks JSON: {exc}")
        return

    pending_blocks = []
    for index, block_data in enumerate(blocks_data):
        if not isinstance(block_data, dict):
            messages.warning(request, f"Block #{index + 1}: invalid format, skipped.")
            continue
        block_type = block_data.get("block_type", "")
        data = block_data.get("data", {})
        try:
            validate_block_data(block_type, data)
        except ValidationError as exc:
            detail = exc.messages[0] if exc.messages else "Validation error."
            messages.warning(request, f"Block #{index + 1} ({block_type}): {detail}")
            continue
        pending_blocks.append(
            CMSBlock(
                page=page,
                block_type=block_type,
                sort_order=index,
                admin_label=block_data.get("admin_label", ""),
                data=data,
            )
        )

    with transaction.atomic():
        page.blocks.all().delete()
        if pending_blocks:
            CMSBlock.objects.bulk_create(pending_blocks)
    transaction.on_commit(lambda: cache.delete(f"cms:page:{page.route}"))


def preview_store_response(request):
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed."}, status=405)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Invalid JSON."}, status=400)
    token = uuid.uuid4().hex
    data["expires_at"] = (timezone.now() + timedelta(seconds=600)).isoformat()
    cache.set(f"cms:preview:{token}", data, timeout=600)
    return JsonResponse({"token": token})


def assets_list_response(request):
    if request.method != "GET":
        return JsonResponse({"detail": "Method not allowed."}, status=405)

    query = request.GET.get("q", "").strip()
    try:
        limit = int(request.GET.get("limit", "50"))
    except ValueError:
        limit = 50
    limit = max(1, min(limit, 100))

    queryset = CMSAsset.objects.all().order_by("-updated_at", "name")
    if query:
        queryset = queryset.filter(name__icontains=query)

    total = queryset.count()
    assets = [serialize_asset(asset) for asset in queryset[:limit]]
    return JsonResponse({"assets": assets, "total": total})


def assets_upload_response(request):
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed."}, status=405)

    uploaded = request.FILES.get("file")
    if uploaded is None:
        return JsonResponse({"detail": "Select a file to upload."}, status=400)

    default_name = os.path.splitext(uploaded.name or "")[0] or uploaded.name or "CMS Asset"
    name = (request.POST.get("name") or default_name).strip()[:200] or "CMS Asset"
    asset = CMSAsset(name=name, file=uploaded)
    try:
        asset.full_clean()
    except ValidationError as exc:
        return JsonResponse(_validation_error_payload(exc), status=400)

    asset.save()
    return JsonResponse({"asset": serialize_asset(asset)}, status=201)


def route_conflict_response(request):
    route = request.GET.get("route", "")
    page_id = request.GET.get("page_id")
    normalized_route = normalize_cms_route(route)
    try:
        normalized_route = validate_cms_route(normalized_route)
    except ValidationError as exc:
        return JsonResponse(
            {
                "normalized_route": normalized_route,
                "has_conflict": False,
                "is_valid": False,
                "message": exc.messages[0],
            }
        )

    conflict_qs = CMSPage.objects.filter(route=normalized_route)
    if page_id:
        conflict_qs = conflict_qs.exclude(pk=page_id)
    conflict = conflict_qs.values("title", "status").first()
    return JsonResponse(
        {
            "normalized_route": normalized_route,
            "has_conflict": bool(conflict),
            "is_valid": True,
            "message": f'Already used by "{conflict["title"]}" ({conflict["status"]}).' if conflict else "",
        }
    )
