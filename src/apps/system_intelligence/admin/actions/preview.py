"""Block payloads for the System Intelligence CMS action preview.

The preview page frames the SPA's /_block-preview once per block and posts each block to its
frame (static/system_intelligence/js/action-preview.js), the protocol the CMS block editor uses,
so a proposal renders with the public site's own components and CSS. Block HTML is sanitized
the way the public API serves it.
"""

import secrets

from apps.cms.services.sanitization import sanitize_block_data


def preview_items(blocks):
    """One entry per block: its admin label, a per-frame nonce and the block to post."""
    items = []
    for index, block in enumerate(item for item in blocks if isinstance(item, dict)):
        data = block.get("data") if isinstance(block.get("data"), dict) else {}
        block_type = str(block.get("block_type") or "block")
        items.append(
            {
                "label": block.get("admin_label") or block_type.replace("_", " ").title(),
                "nonce": secrets.token_hex(18),
                "block": {"block_type": block_type, "sort_order": index, "data": sanitize_block_data(data)},
            }
        )
    return items
