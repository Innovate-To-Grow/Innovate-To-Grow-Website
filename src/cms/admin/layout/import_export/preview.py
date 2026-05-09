"""Stylesheet import preview helpers."""

from cms.models import StyleSheet

from .rows import normalize_stylesheet_row


def preview_stylesheet_import(stylesheets_data):
    existing_by_name = {sheet.name: sheet for sheet in StyleSheet.objects.all()}
    seen_names = set()
    normalized_rows = []
    results = []

    for index, row in enumerate(stylesheets_data):
        result = {"name": "", "display_name": "", "action": "create", "errors": [], "success": False}
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


def mark_results_executed(results):
    return [{**result, "success": not result["errors"]} for result in results]
