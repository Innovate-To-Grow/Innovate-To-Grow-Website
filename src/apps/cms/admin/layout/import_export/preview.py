"""Stylesheet import preview helpers."""

from apps.cms.models import StyleSheet

from .rows import normalize_stylesheet_row


def _preview_row(row, index, existing_by_name, seen_names):
    """One row's preview result, and its normalized data when it can be imported (else None)."""
    result = {"name": "", "display_name": "", "action": "create", "errors": [], "success": False}
    normalized = normalize_stylesheet_row(row, index=index)
    if normalized["errors"]:
        result.update(name=normalized["name"], display_name=normalized["display_name"], errors=normalized["errors"])
        return result, None

    name = normalized["data"]["name"]
    result.update(
        name=name,
        display_name=normalized["data"]["display_name"],
        action="update" if name in existing_by_name else "create",
    )
    if name in seen_names:
        result["errors"] = [f"Duplicate stylesheet name '{name}' in import file."]
        return result, None
    return result, normalized["data"]


def preview_stylesheet_import(stylesheets_data):
    existing_by_name = {sheet.name: sheet for sheet in StyleSheet.objects.all()}
    seen_names = set()
    normalized_rows = []
    results = []

    for index, row in enumerate(stylesheets_data):
        result, data = _preview_row(row, index, existing_by_name, seen_names)
        results.append(result)
        if data is not None:
            seen_names.add(data["name"])
            normalized_rows.append(data)

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


def mark_results_executed(results):
    return [{**result, "success": not result["errors"]} for result in results]
