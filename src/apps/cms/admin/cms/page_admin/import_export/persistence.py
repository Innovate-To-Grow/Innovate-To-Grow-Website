from django.core.cache import cache
from django.db import transaction

from apps.cms.admin.cms.page_admin.import_export.export import export_pages_response as export_pages_response
from apps.cms.models import CMSBlock, CMSPage
from apps.cms.models.content.cms.block_types import normalize_block_data_for_storage


def _page_payload(page_data, default_status):
    return {
        "slug": page_data.get("slug", ""),
        "route": page_data.get("route", f"/{page_data.get('slug', '')}"),
        "title": page_data.get("title", ""),
        "meta_description": page_data.get("meta_description", ""),
        "page_css_class": page_data.get("page_css_class", ""),
        "status": page_data.get("status", default_status),
        "sort_order": page_data.get("sort_order", 0),
    }


def upsert_page(page_data, existing, default_status):
    payload = _page_payload(page_data, default_status)
    if existing:
        for key, value in payload.items():
            setattr(existing, key, value)
        existing.full_clean()
        existing.save()
        existing.blocks.all().delete()
        return existing
    page = CMSPage(**payload)
    page.full_clean()
    page.save()
    return page


def replace_page_blocks(page, blocks_data):
    for index, block_data in enumerate(blocks_data):
        block_type = block_data.get("block_type")
        CMSBlock.objects.create(
            page=page,
            block_type=block_type,
            sort_order=block_data.get("sort_order", index),
            admin_label=block_data.get("admin_label", ""),
            data=normalize_block_data_for_storage(block_type, block_data.get("data", {})),
        )
    transaction.on_commit(lambda route=page.route: cache.delete(f"cms:page:{route}"))
