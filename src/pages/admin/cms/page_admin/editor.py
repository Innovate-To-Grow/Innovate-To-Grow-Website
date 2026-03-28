import json
import uuid
from datetime import timedelta

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone

from pages.models import BLOCK_SCHEMAS, BLOCK_TYPE_CHOICES, CMSBlock, CMSPage, validate_block_data
from pages.models.pages.cms.cms_page import normalize_cms_route, validate_cms_route


def build_editor_context(obj=None):
    from django.conf import settings as django_settings

    context = {
        "block_schemas_json": json.dumps(BLOCK_SCHEMAS),
        "block_type_choices_json": json.dumps(BLOCK_TYPE_CHOICES),
        "route_check_url": reverse("admin:pages_cmspage_route_conflict"),
        "current_page_id": str(obj.pk) if obj else "",
        "current_page_route": obj.route if obj else "",
        "frontend_url": (getattr(django_settings, "FRONTEND_URL", "") or "").rstrip("/"),
    }
    if not obj:
        context["initial_blocks_json"] = "[]"
        return context

    blocks = obj.blocks.filter(is_deleted=False).order_by("sort_order")
    context["initial_blocks_json"] = json.dumps(
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

    page.blocks.filter(is_deleted=False).update(is_deleted=True, deleted_at=timezone.now())
    for index, block_data in enumerate(blocks_data):
        block_type = block_data.get("block_type", "")
        data = block_data.get("data", {})
        try:
            validate_block_data(block_type, data)
        except Exception as exc:  # noqa: BLE001
            messages.warning(request, f"Block #{index + 1} ({block_type}): {exc}")
            continue
        CMSBlock.objects.create(
            page=page,
            block_type=block_type,
            sort_order=index,
            admin_label=block_data.get("admin_label", ""),
            data=data,
        )
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

    conflict_qs = CMSPage.all_objects.filter(route=normalized_route)
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
