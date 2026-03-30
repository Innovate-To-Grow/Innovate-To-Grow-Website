import json

from django.contrib import messages
from django.core.cache import cache
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from cms.models import BLOCK_TYPE_CHOICES, CMSBlock, CMSPage, validate_block_data


def export_pages_response(queryset):
    content = json.dumps(
        {
            "version": 1,
            "exported_at": timezone.now().isoformat(),
            "pages": [serialize_page(page) for page in queryset.prefetch_related("blocks")],
        },
        indent=2,
        cls=DjangoJSONEncoder,
        ensure_ascii=False,
    )
    response = HttpResponse(content, content_type="application/json")
    response["Content-Disposition"] = (
        f'attachment; filename="cms_export_{timezone.now().strftime("%Y%m%d_%H%M%S")}.json"'
    )
    return response


def render_json_import(
    admin_obj, request, *, title, template_name, pages_data=None, require_upload=False, validate_required=False
):
    context = {**admin_obj.admin_site.each_context(request), "title": title, "opts": admin_obj.model._meta}
    if pages_data is None:
        if request.method != "POST":
            return render(request, template_name, context)
        pages_data = load_uploaded_pages(request, context, template_name)
        if pages_data is None:
            return render(request, template_name, context)

    action = request.POST.get("action") if request.method == "POST" else None
    results = process_page_data(
        pages_data,
        action=action or "dry_run",
        default_status="published" if not require_upload else "draft",
        validate_required=validate_required,
    )

    if action == "execute":
        success_count = sum(1 for result in results if result.get("success"))
        error_count = sum(1 for result in results if result.get("errors"))
        if success_count:
            messages.success(request, f"Successfully imported {success_count} page(s).")
            transaction.on_commit(lambda: cache.delete("layout:data"))
        if error_count:
            messages.warning(request, f"{error_count} page(s) had errors.")

    context.update(
        {
            "results": results,
            "total_pages": len(pages_data) if not require_upload else None,
            "is_dry_run": action != "execute",
            "has_results": action is not None if not require_upload else True,
        }
    )
    return render(request, template_name, context)


def load_uploaded_pages(request, context, template_name):
    json_file = request.FILES.get("json_file")
    if not json_file:
        messages.error(request, "Please select a JSON file to import.")
        return None
    try:
        bundle = json.loads(json_file.read().decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        messages.error(request, f"Invalid JSON file: {exc}")
        return None
    if not isinstance(bundle, dict) or not isinstance(bundle.get("pages"), list):
        messages.error(request, "Invalid format: expected a JSON object with a 'pages' list.")
        return None
    return bundle["pages"]


def process_page_data(pages_data, *, action, default_status, validate_required):
    block_type_keys = {choice[0] for choice in BLOCK_TYPE_CHOICES}
    results = []
    for page_data in pages_data:
        result, blocks_data, existing = validate_page_data(page_data, block_type_keys, validate_required)
        if not result["errors"] and action == "execute":
            try:
                page = upsert_page(page_data, existing, default_status)
                replace_page_blocks(page, blocks_data)
                result["success"] = True
            except Exception as exc:  # noqa: BLE001
                result["errors"].append(str(exc))
        results.append(result)
    return results


def validate_page_data(page_data, block_type_keys, validate_required):
    slug = page_data.get("slug", "")
    title = page_data.get("title", "")
    route = page_data.get("route", "")
    result = {"slug": slug, "title": title, "errors": [], "action": "", "block_count": len(page_data.get("blocks", []))}
    if validate_required:
        if not slug:
            result["errors"].append("Missing 'slug'.")
        if not route:
            result["errors"].append("Missing 'route'.")
        if not title:
            result["errors"].append("Missing 'title'.")
    for index, block_data in enumerate(page_data.get("blocks", [])):
        block_type = block_data.get("block_type", "")
        if block_type not in block_type_keys:
            result["errors"].append(f"Block #{index + 1}: unknown type '{block_type}'.")
            continue
        try:
            validate_block_data(block_type, block_data.get("data", {}))
        except Exception as exc:  # noqa: BLE001
            result["errors"].append(f"Block #{index + 1} ({block_type}): {exc}")
    existing = CMSPage.objects.filter(slug=slug).first() if slug else None
    result["action"] = "update" if existing else "create"
    return result, page_data.get("blocks", []), existing


def upsert_page(page_data, existing, default_status):
    payload = {
        "slug": page_data.get("slug", ""),
        "route": page_data.get("route", f"/{page_data.get('slug', '')}"),
        "title": page_data.get("title", ""),
        "meta_description": page_data.get("meta_description", ""),
        "page_css_class": page_data.get("page_css_class", ""),
        "status": page_data.get("status", default_status),
        "sort_order": page_data.get("sort_order", 0),
    }
    if existing:
        for key, value in payload.items():
            setattr(existing, key, value)
        existing.save()
        existing.blocks.filter(is_deleted=False).update(is_deleted=True, deleted_at=timezone.now())
        return existing
    return CMSPage.objects.create(**payload)


def replace_page_blocks(page, blocks_data):
    for index, block_data in enumerate(blocks_data):
        CMSBlock.objects.create(
            page=page,
            block_type=block_data.get("block_type"),
            sort_order=block_data.get("sort_order", index),
            admin_label=block_data.get("admin_label", ""),
            data=block_data.get("data", {}),
        )
    transaction.on_commit(lambda route=page.route: cache.delete(f"cms:page:{route}"))


def serialize_page(page):
    return {
        "slug": page.slug,
        "route": page.route,
        "title": page.title,
        "meta_description": page.meta_description,
        "page_css_class": page.page_css_class,
        "status": page.status,
        "sort_order": page.sort_order,
        "blocks": [
            {
                "block_type": block.block_type,
                "sort_order": block.sort_order,
                "admin_label": block.admin_label,
                "data": block.data,
            }
            for block in page.blocks.filter(is_deleted=False).order_by("sort_order")
        ],
    }
