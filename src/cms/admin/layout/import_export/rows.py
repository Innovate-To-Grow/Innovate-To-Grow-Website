"""Stylesheet import row normalization."""

from django.core.exceptions import ValidationError

from cms.models import StyleSheet


def normalize_stylesheet_row(row, *, index):
    result = {"name": "", "display_name": "", "errors": [], "data": None}
    if not isinstance(row, dict):
        result["errors"].append(f"Entry #{index + 1}: expected an object.")
        return result

    raw_name = row.get("name", "")
    raw_display_name = row.get("display_name", "")
    result["name"] = raw_name if isinstance(raw_name, str) else ""
    result["display_name"] = raw_display_name if isinstance(raw_display_name, str) else ""

    stylesheet = StyleSheet(
        name=raw_name,
        display_name=raw_display_name,
        description=row.get("description", ""),
        css=row.get("css", ""),
        is_active=row.get("is_active", True),
        sort_order=row.get("sort_order", 0),
    )
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
