"""Stylesheet import admin view helpers."""

import json

from django.contrib import messages
from django.shortcuts import render

from .persistence import sync_stylesheets
from .preview import mark_results_executed, preview_stylesheet_import


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

    context.update({"results": results, "is_dry_run": action != "execute", "has_results": True})
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
