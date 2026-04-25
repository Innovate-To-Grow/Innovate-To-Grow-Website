import json
from typing import Any

from django.core.serializers.json import DjangoJSONEncoder

from core.models.base.system_intelligence import SystemIntelligenceActionRequest

from .comparison_text import extract_block_text, limit_comparison_text
from .constants import COMPARISON_MAX_BLOCKS, COMPARISON_MAX_FIELDS
from .utils import json_safe


def build_diff(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    diff = []
    for key in sorted(set(before) | set(after)):
        before_value = before.get(key)
        after_value = after.get(key)
        if before_value == after_value:
            continue
        diff.append(
            {"field": key, "before": compact_diff_value(before_value), "after": compact_diff_value(after_value)}
        )
    return diff


def compact_diff_value(value: Any) -> Any:
    if isinstance(value, list):
        return {"count": len(value), "items": json_safe(value[:3])}
    if isinstance(value, dict):
        text = json.dumps(value, cls=DjangoJSONEncoder, default=str)
        if len(text) > 400:
            return {"summary": text[:400] + "..."}
    return json_safe(value)


def action_comparison(action: SystemIntelligenceActionRequest, payload: dict[str, Any]) -> dict[str, Any]:
    comparison = payload.get("comparison")
    if isinstance(comparison, dict):
        return comparison
    if action.action_type == SystemIntelligenceActionRequest.ACTION_CMS_PAGE_UPDATE:
        return build_cms_comparison(action.before_snapshot or {}, action.after_snapshot or {})
    return {}


def build_cms_comparison(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before = before or {}
    after = after or {}
    field_changes = []
    for field in ("title", "route", "status", "meta_description", "page_css_class", "sort_order"):
        if before.get(field) == after.get(field):
            continue
        field_changes.append(
            {
                "field": field,
                "before": limit_comparison_text(before.get(field)),
                "after": limit_comparison_text(after.get(field)),
            }
        )
    blocks, blocks_truncated = cms_block_comparisons(before.get("blocks") or [], after.get("blocks") or [])
    return {
        "type": "cms_page",
        "page_title": after.get("title") or before.get("title") or "CMS page",
        "page_route": after.get("route") or before.get("route") or "",
        "fields": field_changes[:COMPARISON_MAX_FIELDS],
        "blocks": blocks,
        "truncated": blocks_truncated or len(field_changes) > COMPARISON_MAX_FIELDS,
    }


def cms_block_comparisons(before_blocks: list[dict[str, Any]], after_blocks: list[dict[str, Any]]):
    before_map = {block_key(block, index): block for index, block in enumerate(before_blocks)}
    after_map = {block_key(block, index): block for index, block in enumerate(after_blocks)}
    comparisons = []
    for key in sorted(set(before_map) | set(after_map)):
        before = before_map.get(key) or {}
        after = after_map.get(key) or {}
        if before == after:
            continue
        comparisons.append(
            {
                "label": block_label(before, after),
                "block_type": after.get("block_type") or before.get("block_type") or "",
                "sort_order": after.get("sort_order", before.get("sort_order", "")),
                "changed_keys": changed_block_keys(before, after),
                "before_text": extract_block_text(before),
                "after_text": extract_block_text(after),
            }
        )
    return comparisons[:COMPARISON_MAX_BLOCKS], len(comparisons) > COMPARISON_MAX_BLOCKS


def block_key(block: dict[str, Any], fallback_index: int) -> tuple[int, str, int]:
    sort_order = block.get("sort_order")
    if not isinstance(sort_order, int):
        sort_order = fallback_index
    return (sort_order, str(block.get("block_type") or ""), fallback_index)


def block_label(before: dict[str, Any], after: dict[str, Any]) -> str:
    block = after or before
    if block.get("admin_label"):
        return str(block["admin_label"])
    data = block.get("data") if isinstance(block.get("data"), dict) else {}
    for key in ("heading", "title", "label", "name"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return limit_comparison_text(value, 80)
    block_type = str(block.get("block_type") or "block").replace("_", " ").title()
    sort_order = block.get("sort_order")
    return f"{block_type} block" if sort_order in (None, "") else f"{block_type} block #{sort_order}"


def changed_block_keys(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    keys = ["admin_label"] if before.get("admin_label") != after.get("admin_label") else []
    before_data = before.get("data") if isinstance(before.get("data"), dict) else {}
    after_data = after.get("data") if isinstance(after.get("data"), dict) else {}
    for key in sorted(set(before_data) | set(after_data)):
        if before_data.get(key) != after_data.get(key):
            keys.append(key)
    return keys[:12]
