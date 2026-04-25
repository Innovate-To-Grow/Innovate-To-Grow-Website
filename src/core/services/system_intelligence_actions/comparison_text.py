import json
import re
from html import unescape
from typing import Any

from django.core.serializers.json import DjangoJSONEncoder

from .constants import COMPARISON_TEXT_LIMIT


def extract_block_text(block: dict[str, Any]) -> str:
    if not block:
        return ""
    data = block.get("data", {})
    parts = []
    collect_text_parts(data, parts)
    text = "\n".join(part for part in parts if part)
    if not text:
        text = json.dumps(data, cls=DjangoJSONEncoder, default=str)
    return limit_comparison_text(text)


def collect_text_parts(value: Any, parts: list[str]) -> None:
    if isinstance(value, str):
        cleaned = clean_display_text(value)
        if cleaned:
            parts.append(cleaned)
        return
    if isinstance(value, list):
        for item in value:
            collect_text_parts(item, parts)
        return
    if isinstance(value, dict):
        priority_keys = (
            "heading",
            "subheading",
            "title",
            "label",
            "name",
            "question",
            "answer",
            "body_html",
            "body",
            "content",
            "text",
            "description",
            "summary",
            "caption",
        )
        seen = set()
        for key in priority_keys:
            if key in value:
                seen.add(key)
                collect_text_parts(value[key], parts)
        for key, nested in value.items():
            if key in seen or key in {"url", "href", "src", "image_url", "source_url"}:
                continue
            collect_text_parts(nested, parts)


def clean_display_text(value: str) -> str:
    value = unescape(value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def limit_comparison_text(value: Any, limit: int = COMPARISON_TEXT_LIMIT) -> str:
    if value is None:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, cls=DjangoJSONEncoder, default=str)
    text = clean_display_text(text)
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."
