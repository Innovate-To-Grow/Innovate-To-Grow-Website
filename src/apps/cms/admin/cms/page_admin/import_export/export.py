import json

from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpResponse
from django.utils import timezone


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
            for block in page.blocks.all().order_by("sort_order")
        ],
    }
