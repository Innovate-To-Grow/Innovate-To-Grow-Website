import json

from django.contrib import messages
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from cms.models import StyleSheet
from cms.views.views import LAYOUT_CACHE_KEY, LAYOUT_STYLESHEET_CACHE_KEY

STYLESHEET_BUNDLE_VERSION = 1


def export_stylesheets_response(queryset):
    content = json.dumps(
        {
            "version": STYLESHEET_BUNDLE_VERSION,
            "exported_at": timezone.now().isoformat(),
            "stylesheets": [serialize_stylesheet(sheet) for sheet in queryset.order_by("sort_order", "name")],
        },
        indent=2,
        ensure_ascii=False,
    )
    response = HttpResponse(content, content_type="application/json")
    response["Content-Disposition"] = (
        f'attachment; filename="stylesheets_export_{timezone.now().strftime("%Y%m%d_%H%M%S")}.json"'
    )
    return response


def render_stylesheet_import(admin_obj, request, *, title, template_name):
    context = {**admin_obj.admin_site.each_context(request), "title": title, "opts": admin_obj.model._meta}
    if request.method != "POST":
        return render(request, template_name, context)

    stylesheets_data = load_uploaded_stylesheets(request)
    if stylesheets_data is None:
        return render(request, template_name, context)

    action = request.POST.get("action") or "dry_run"
    results, normalized_rows, has_errors = preview_stylesheet_import(stylesheets_data)

    if action == "execute":
        if has_errors:
            messages.warning(request, "Import not executed because validation errors were found.")
        else:
            sync_stylesheets(normalized_rows)
            success_count = len(normalized_rows)
            delete_count = sum(1 for result in results if result["action"] == "delete")
            messages.success(request, f"Successfully imported {success_count} stylesheet(s).")
            if delete_count:
                messages.success(request, f"Deleted {delete_count} stylesheet(s) not present in the import file.")
            results = mark_results_executed(results)

    context.update(
        {
            "results": results,
            "is_dry_run": action != "execute",
            "has_results": True,
        }
    )
    return render(request, template_name, context)


def load_uploaded_stylesheets(request):
    json_file = request.FILES.get("json_file")
    if not json_file:
        messages.error(request, "Please select a JSON file to import.")
        return None
    try:
        bundle = json.loads(json_file.read().decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        messages.error(request, f"Invalid JSON file: {exc}")
        return None
    if not isinstance(bundle, dict) or not isinstance(bundle.get("stylesheets"), list):
        messages.error(request, "Invalid format: expected a JSON object with a 'stylesheets' list.")
        return None
    return bundle["stylesheets"]


def preview_stylesheet_import(stylesheets_data):
    existing_by_name = {sheet.name: sheet for sheet in StyleSheet.objects.all()}
    seen_names = set()
    normalized_rows = []
    results = []

    for index, row in enumerate(stylesheets_data):
        result = {
            "name": "",
            "display_name": "",
            "action": "create",
            "errors": [],
            "success": False,
        }
        normalized = normalize_stylesheet_row(row, index=index)
        if normalized["errors"]:
            result.update(
                {
                    "name": normalized["name"],
                    "display_name": normalized["display_name"],
                    "errors": normalized["errors"],
                    "action": "create",
                }
            )
            results.append(result)
            continue

        name = normalized["data"]["name"]
        if name in seen_names:
            result.update(
                {
                    "name": name,
                    "display_name": normalized["data"]["display_name"],
                    "errors": [f"Duplicate stylesheet name '{name}' in import file."],
                    "action": "update" if name in existing_by_name else "create",
                }
            )
            results.append(result)
            continue

        seen_names.add(name)
        existing = existing_by_name.get(name)
        result.update(
            {
                "name": name,
                "display_name": normalized["data"]["display_name"],
                "action": "update" if existing else "create",
            }
        )
        results.append(result)
        normalized_rows.append(normalized["data"])

    for sheet in StyleSheet.objects.exclude(name__in=seen_names).order_by("sort_order", "name"):
        results.append(
            {
                "name": sheet.name,
                "display_name": sheet.display_name,
                "action": "delete",
                "errors": [],
                "success": False,
            }
        )

    has_errors = any(result["errors"] for result in results)
    return results, normalized_rows, has_errors


def normalize_stylesheet_row(row, *, index):
    result = {"name": "", "display_name": "", "errors": [], "data": None}
    if not isinstance(row, dict):
        result["errors"].append(f"Entry #{index + 1}: expected an object.")
        return result

    raw_name = row.get("name", "")
    raw_display_name = row.get("display_name", "")
    result["name"] = raw_name if isinstance(raw_name, str) else ""
    result["display_name"] = raw_display_name if isinstance(raw_display_name, str) else ""

    payload = {
        "name": raw_name,
        "display_name": raw_display_name,
        "description": row.get("description", ""),
        "css": row.get("css", ""),
        "is_active": row.get("is_active", True),
        "sort_order": row.get("sort_order", 0),
    }

    stylesheet = StyleSheet(**payload)
    try:
        stylesheet.full_clean(validate_unique=False)
    except ValidationError as exc:
        for field_errors in exc.message_dict.values():
            result["errors"].extend(field_errors)
        return result

    result["name"] = stylesheet.name
    result["display_name"] = stylesheet.display_name
    result["data"] = {
        "name": stylesheet.name,
        "display_name": stylesheet.display_name,
        "description": stylesheet.description,
        "css": stylesheet.css,
        "is_active": stylesheet.is_active,
        "sort_order": stylesheet.sort_order,
    }
    return result


def sync_stylesheets(normalized_rows):
    import_names = [row["name"] for row in normalized_rows]

    with transaction.atomic():
        existing_by_name = {sheet.name: sheet for sheet in StyleSheet.objects.filter(name__in=import_names)}
        for row in normalized_rows:
            stylesheet = existing_by_name.get(row["name"])
            if stylesheet is None:
                StyleSheet.objects.create(**row)
                continue

            for field, value in row.items():
                setattr(stylesheet, field, value)
            stylesheet.save()

        StyleSheet.objects.exclude(name__in=import_names).delete()
        transaction.on_commit(clear_layout_caches)


def clear_layout_caches():
    cache.delete(LAYOUT_CACHE_KEY)
    cache.delete(LAYOUT_STYLESHEET_CACHE_KEY)


def mark_results_executed(results):
    executed = []
    for result in results:
        executed.append(
            {
                **result,
                "success": not result["errors"],
            }
        )
    return executed


def serialize_stylesheet(sheet):
    return {
        "name": sheet.name,
        "display_name": sheet.display_name,
        "description": sheet.description,
        "css": sheet.css,
        "is_active": sheet.is_active,
        "sort_order": sheet.sort_order,
    }
