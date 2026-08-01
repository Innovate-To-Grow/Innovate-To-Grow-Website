"""Block persistence helpers for the CMS page editor."""

import json

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.cms.models import CMSBlock, CMSPage, validate_block_data
from apps.cms.models.content.cms.block_types import normalize_block_data_for_storage


def save_blocks_from_json(request, page, messages):
    blocks_json = request.POST.get("blocks_json", "")
    if not blocks_json:
        return
    try:
        blocks_data = json.loads(blocks_json)
        if not isinstance(blocks_data, list):
            messages.error(request, "Invalid blocks data: expected a JSON array.")
            return
    except json.JSONDecodeError:
        messages.error(request, "Invalid blocks JSON: could not parse input.")
        return

    pending_blocks = []
    for index, block_data in enumerate(blocks_data):
        pending = _build_pending_block(page, index, block_data, messages, request)
        if pending is not None:
            pending_blocks.append(pending)

    with transaction.atomic():
        # Share the parent-page mutex with AI approvals/imports, then lock the
        # exact child set before destructive replacement.
        locked_page = CMSPage.objects.select_for_update().get(pk=page.pk)
        list(CMSBlock.objects.select_for_update().filter(page=locked_page))
        CMSBlock.objects.filter(page=locked_page).delete()
        if pending_blocks:
            for block in pending_blocks:
                block.page = locked_page
            CMSBlock.objects.bulk_create(pending_blocks)
    transaction.on_commit(lambda: cache.delete(f"cms:page:{page.route}"))


def _build_pending_block(page, index, block_data, messages, request):
    if not isinstance(block_data, dict):
        messages.warning(request, f"Block #{index + 1}: invalid format, skipped.")
        return None
    block_type = block_data.get("block_type", "")
    data = block_data.get("data", {})
    try:
        validate_block_data(block_type, data)
    except ValidationError as exc:
        detail = exc.messages[0] if exc.messages else "Validation error."
        messages.warning(request, f"Block #{index + 1} ({block_type}): {detail}")
        return None
    except (TypeError, AttributeError, KeyError):
        messages.warning(request, f"Block #{index + 1} ({block_type}): Invalid block data format.")
        return None

    data = normalize_block_data_for_storage(block_type, data)
    return CMSBlock(
        page=page,
        block_type=block_type,
        sort_order=index,
        admin_label=block_data.get("admin_label", ""),
        data=data,
    )
