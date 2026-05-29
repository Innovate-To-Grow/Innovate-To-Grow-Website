"""CMS block preview rendering for System Intelligence actions."""

import re
from urllib.parse import urlparse

from django.utils.html import conditional_escape, format_html, format_html_join

from cms.services.sanitize import sanitize_html_for_render

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")


def _render_preview_blocks(blocks):
    return format_html_join("", "{}", ((_render_preview_block(block),) for block in blocks))


def _render_preview_block(block):
    if not isinstance(block, dict):
        return ""
    data = block.get("data") if isinstance(block.get("data"), dict) else {}
    block_type = block.get("block_type") or "block"
    label = block.get("admin_label") or block_type.replace("_", " ").title()
    body = _render_block_body(block_type, data)
    if not body:
        body = format_html('<p class="si-action-preview-empty">No previewable content for this block.</p>')
    return format_html(
        '<section class="si-action-preview-block si-action-preview-block--{}">'
        '<div class="si-action-preview-block-meta">{}</div>{}</section>',
        block_type,
        label,
        body,
    )


def _render_block_body(block_type, data):
    if block_type == "rich_text":
        return _render_heading_and_html(data, "cms-rich-text")
    if block_type == "image_text":
        return _render_heading_and_html(data, "cms-image-text")
    if block_type == "section_group":
        return _render_section_group(data)
    if block_type == "faq_list":
        return _render_faq_list(data)
    if block_type == "link_list":
        return _render_link_list(data)
    if block_type == "table":
        return _render_table(data)
    return _render_heading_and_html(data, f"cms-{block_type.replace('_', '-')}")


def _render_heading_and_html(data, css_class):
    parts = []
    heading = data.get("heading")
    if heading:
        level = _heading_level(data.get("heading_level"), default=2)
        parts.append(format_html("<h{}>{}</h{}>", level, heading, level))
    if data.get("body_html"):
        parts.append(format_html('<div class="{}">{}</div>', css_class, sanitize_html_for_render(data["body_html"])))
    return format_html_join("", "{}", ((part,) for part in parts))


def _render_section_group(data):
    sections = data.get("sections")
    if not isinstance(sections, list):
        return _render_heading_and_html(data, "cms-section-group")
    return format_html_join(
        "",
        '<section class="cms-section-group"><h{}>{}</h{}><div>{}</div></section>',
        (
            (
                _heading_level(section.get("heading_level"), default=2),
                section.get("heading", ""),
                _heading_level(section.get("heading_level"), default=2),
                sanitize_html_for_render(section.get("body_html")),
            )
            for section in sections
            if isinstance(section, dict)
        ),
    )


def _render_faq_list(data):
    faqs = data.get("items") or data.get("faqs")
    if not isinstance(faqs, list):
        return _render_heading_and_html(data, "cms-faq-list")
    return format_html_join(
        "",
        '<section class="cms-faq-list"><h3>{}</h3><div>{}</div></section>',
        (
            (item.get("question") or item.get("heading") or "Question", sanitize_html_for_render(item.get("answer")))
            for item in faqs
            if isinstance(item, dict)
        ),
    )


def _render_link_list(data):
    items = data.get("items") or data.get("links")
    if not isinstance(items, list):
        return _render_heading_and_html(data, "cms-link-list")
    return format_html(
        '<ul class="cms-link-list-items">{}</ul>',
        format_html_join(
            "",
            '<li><a href="{}">{}</a>{}</li>',
            (
                (
                    _safe_href(item.get("url", "#")),
                    _link_label(item),
                    format_html(" - {}", item.get("description", "")) if item.get("description") else "",
                )
                for item in items
                if isinstance(item, dict)
            ),
        ),
    )


def _render_table(data):
    rows = data.get("rows")
    if not isinstance(rows, list):
        return _render_heading_and_html(data, "cms-table")
    return format_html(
        '<table class="cms-table"><tbody>{}</tbody></table>',
        format_html_join(
            "",
            "<tr>{}</tr>",
            (
                (format_html_join("", "<td>{}</td>", ((conditional_escape(cell),) for cell in row)),)
                for row in rows
                if isinstance(row, list)
            ),
        ),
    )


def _safe_href(url):
    if not isinstance(url, str):
        return "#"
    href = _CONTROL_CHAR_RE.sub("", url).strip()
    if not href or href.startswith(("//", "\\\\")):
        return "#"
    parsed = urlparse(href)
    if parsed.scheme and parsed.scheme not in {"http", "https"}:
        return "#"
    if parsed.netloc and not parsed.scheme:
        return "#"
    return href


def _link_label(item):
    title = item.get("title") or item.get("label")
    if title:
        return title
    url = item.get("url")
    return url if _safe_href(url) != "#" else "Link"


def _heading_level(value, default):
    try:
        level = int(value or default)
    except (TypeError, ValueError):
        level = default
    return min(max(level, 1), 6)
