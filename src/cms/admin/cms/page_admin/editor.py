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

from cms.models import BLOCK_SCHEMAS, BLOCK_TYPE_CHOICES, CMSBlock, CMSPage, validate_block_data
from cms.models.content.cms.cms_page import EMBED_SLUG_RE, normalize_cms_route, validate_cms_route


def build_editor_context(obj=None):
    from django.conf import settings as django_settings

    context = {
        "block_schemas_json": json.dumps(BLOCK_SCHEMAS),
        "block_type_choices_json": json.dumps(BLOCK_TYPE_CHOICES),
        "route_check_url": reverse("admin:cms_cmspage_route_conflict"),
        "current_page_id": str(obj.pk) if obj else "",
        "current_page_route": obj.route if obj else "",
        "frontend_url": (getattr(django_settings, "FRONTEND_URL", "") or "").rstrip("/"),
    }
    if not obj:
        context["initial_blocks_json"] = "[]"
        context["initial_embed_configs_json"] = "[]"
        return context

    blocks = obj.blocks.all().order_by("sort_order")
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
    context["initial_embed_configs_json"] = json.dumps(obj.embed_configs or [], cls=DjangoJSONEncoder)
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

    page.blocks.all().delete()
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


def save_embed_configs_from_json(request, page, messages):
    """Persist page-level embed widget configurations.

    Each entry is ``{slug, block_sort_orders, admin_label?}``. Invalid entries
    are dropped with a warning; partial saves are preferred over hard-failing.
    """
    configs_json = request.POST.get("embed_configs_json", "")
    if configs_json == "":
        # Field absent — do not clear existing configs.
        return
    try:
        configs = json.loads(configs_json)
        if not isinstance(configs, list):
            messages.error(request, "Invalid embed configs: expected a JSON array.")
            return
    except json.JSONDecodeError as exc:
        messages.error(request, f"Invalid embed configs JSON: {exc}")
        return

    # The blocks have just been re-created with sort_order = index. Snapshot
    # what's valid so we can reject references to nonexistent positions.
    valid_sort_orders = set(page.blocks.values_list("sort_order", flat=True))

    # Global uniqueness: a slug used on ANOTHER page blocks us.
    reserved_slugs: set[str] = set()
    for other_page in CMSPage.objects.exclude(pk=page.pk).only("embed_configs"):
        for entry in other_page.embed_configs or []:
            slug = (entry or {}).get("slug")
            if slug:
                reserved_slugs.add(slug)

    seen_slugs: set[str] = set()
    clean: list[dict] = []
    for index, entry in enumerate(configs):
        if not isinstance(entry, dict):
            messages.warning(request, f"Embed #{index + 1}: not a JSON object — dropped.")
            continue
        slug = str(entry.get("slug", "") or "").strip().lower()
        admin_label = str(entry.get("admin_label", "") or "").strip()
        sort_orders_raw = entry.get("block_sort_orders") or []
        if not isinstance(sort_orders_raw, list):
            messages.warning(request, f"Embed #{index + 1}: block_sort_orders must be a list — dropped.")
            continue

        if not slug:
            messages.warning(request, f"Embed #{index + 1}: slug is required — dropped.")
            continue
        if not EMBED_SLUG_RE.match(slug):
            messages.warning(
                request,
                f"Embed #{index + 1}: slug '{slug}' must be kebab-case — dropped.",
            )
            continue
        if slug in seen_slugs:
            messages.warning(
                request,
                f"Embed #{index + 1}: slug '{slug}' duplicates another embed on this page — dropped.",
            )
            continue
        if slug in reserved_slugs:
            messages.warning(
                request,
                f"Embed #{index + 1}: slug '{slug}' is already used by another page — dropped.",
            )
            continue

        # De-duplicate and validate block references.
        block_sort_orders: list[int] = []
        for ref in sort_orders_raw:
            try:
                ref_int = int(ref)
            except (TypeError, ValueError):
                continue
            if ref_int not in valid_sort_orders:
                continue
            if ref_int in block_sort_orders:
                continue
            block_sort_orders.append(ref_int)

        if not block_sort_orders:
            messages.warning(
                request,
                f"Embed '{slug}': no valid block references — dropped.",
            )
            continue

        seen_slugs.add(slug)
        clean.append(
            {
                "slug": slug,
                "admin_label": admin_label,
                "block_sort_orders": sorted(block_sort_orders),
            }
        )

    page.embed_configs = clean
    page.save(update_fields=["embed_configs", "updated_at"])


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
