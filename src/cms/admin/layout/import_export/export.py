"""Stylesheet export helpers."""

import json

from django.http import HttpResponse
from django.utils import timezone

import cms.admin.layout.import_export as import_export_api


def export_stylesheets_response(queryset):
    content = json.dumps(
        {
            "version": import_export_api.STYLESHEET_BUNDLE_VERSION,
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


def serialize_stylesheet(sheet):
    return {
        "name": sheet.name,
        "display_name": sheet.display_name,
        "description": sheet.description,
        "css": sheet.css,
        "is_active": sheet.is_active,
        "sort_order": sheet.sort_order,
    }
