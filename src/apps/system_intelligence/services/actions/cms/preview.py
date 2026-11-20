from collections.abc import Iterable

from django.core.cache import cache

from apps.cms.models import CMSBlock, CMSPage


def normalize_cms_blocks(blocks: list[dict]) -> list[dict]:
    if not isinstance(blocks, list):
        from ..engine.exceptions import ActionRequestError

        raise ActionRequestError("blocks must be a list.")
    normalized = []
    for index, block in enumerate(blocks):
        if not isinstance(block, dict):
            from ..engine.exceptions import ActionRequestError

            raise ActionRequestError(f"Block #{index + 1} must be an object.")
        normalized.append(
            {
                "block_type": block.get("block_type", ""),
                "sort_order": index,
                "admin_label": block.get("admin_label", ""),
                "data": block.get("data") or {},
            }
        )
    return normalized


def create_cms_blocks(page: CMSPage, blocks: Iterable[dict]) -> None:
    from apps.cms.models.content.cms.block_types import normalize_block_data_for_storage

    for index, block in enumerate(blocks):
        block_type = block.get("block_type")
        CMSBlock.objects.create(
            page=page,
            block_type=block_type,
            sort_order=index,
            admin_label=block.get("admin_label", ""),
            # Same storage normalization as the admin editor and page import, so
            # e.g. embed_widget schedule ids land in their canonical form.
            data=normalize_block_data_for_storage(block_type, block.get("data") or {}),
        )


def clear_cms_cache(old_route: str, new_route: str, preview_token: str) -> None:
    if old_route:
        cache.delete(f"cms:page:{old_route}")
    cache.delete(f"cms:page:{new_route}")
    if preview_token:
        cache.delete(f"cms:preview:{preview_token}")
