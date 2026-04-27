from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, JsonResponse
from django.template.response import TemplateResponse
from django.utils.html import conditional_escape, format_html, format_html_join
from django.utils.safestring import mark_safe
from django.views.decorators.clickjacking import xframe_options_sameorigin

from cms.services.sanitize import sanitize_html
from core.models.base.system_intelligence import SystemIntelligenceActionRequest
from core.services import system_intelligence_actions
from core.services.system_intelligence_actions.comparison import block_key


def action_approve_view(request, action_id):
    """Approve and apply a pending System Intelligence action request."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    try:
        action = _get_user_action_request(request, action_id)
    except PermissionDenied as exc:
        return JsonResponse({"error": str(exc)}, status=404)
    try:
        action = system_intelligence_actions.approve_action_request(action.id, request.user)
    except (PermissionDenied, system_intelligence_actions.ActionRequestError, ValidationError, ValueError) as exc:
        action.refresh_from_db()
        return JsonResponse(
            {"error": str(exc), "action_request": system_intelligence_actions.serialize_action_request(action)},
            status=400,
        )
    return JsonResponse({"ok": True, "action_request": system_intelligence_actions.serialize_action_request(action)})


def action_reject_view(request, action_id):
    """Reject a pending System Intelligence action request."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    try:
        action = _get_user_action_request(request, action_id)
    except PermissionDenied as exc:
        return JsonResponse({"error": str(exc)}, status=404)
    try:
        action = system_intelligence_actions.reject_action_request(action.id, request.user)
    except system_intelligence_actions.ActionRequestError as exc:
        return JsonResponse(
            {"error": str(exc), "action_request": system_intelligence_actions.serialize_action_request(action)},
            status=400,
        )
    return JsonResponse({"ok": True, "action_request": system_intelligence_actions.serialize_action_request(action)})


@xframe_options_sameorigin
def action_preview_view(request, action_id):
    """Render a same-origin iframe preview for a pending CMS page action."""
    try:
        action = _get_user_action_request(request, action_id)
    except PermissionDenied as exc:
        raise Http404(str(exc)) from exc

    payload = action.payload if isinstance(action.payload, dict) else {}
    page = payload.get("page")
    if action.action_type != SystemIntelligenceActionRequest.ACTION_CMS_PAGE_UPDATE or not isinstance(page, dict):
        raise Http404("Preview not available.")

    preview_blocks = _changed_preview_blocks(action, page)
    return TemplateResponse(
        request,
        "admin/core/system_intelligence_action_preview.html",
        {
            "action": action,
            "page": page,
            "block_html": mark_safe("".join(_render_preview_block(block) for block in preview_blocks)),
            "has_changed_blocks": bool(preview_blocks),
            "has_preview_blocks": bool(preview_blocks),
            "banner_text": "Previewing changed CMS block content. This change is not applied until approved.",
            "empty_text": "No CMS block content changed in this proposal.",
        },
    )


def action_full_preview_view(request, action_id):
    """Render the full proposed CMS page in a new admin preview tab."""
    try:
        action = _get_user_action_request(request, action_id)
    except PermissionDenied as exc:
        raise Http404(str(exc)) from exc

    page = _cms_preview_page(action)
    if page is None:
        raise Http404("Preview not available.")

    blocks = page.get("blocks") if isinstance(page.get("blocks"), list) else []
    return TemplateResponse(
        request,
        "admin/core/system_intelligence_action_preview.html",
        {
            "action": action,
            "page": page,
            "block_html": mark_safe("".join(_render_preview_block(block) for block in blocks)),
            "has_changed_blocks": bool(blocks),
            "has_preview_blocks": bool(blocks),
            "banner_text": "Previewing full proposed CMS page content. This change is not applied until approved.",
            "empty_text": "This proposed CMS page has no block content to preview.",
        },
    )


def _get_user_action_request(request, action_id):
    try:
        return SystemIntelligenceActionRequest.objects.get(id=action_id, conversation__created_by=request.user)
    except SystemIntelligenceActionRequest.DoesNotExist:
        raise PermissionDenied("Action request not found.")


def _cms_preview_page(action):
    if action.action_type != SystemIntelligenceActionRequest.ACTION_CMS_PAGE_UPDATE:
        return None
    cached = cache.get(f"cms:preview:{action.preview_token}") if action.preview_token else None
    if isinstance(cached, dict):
        return cached
    payload = action.payload if isinstance(action.payload, dict) else {}
    page = payload.get("page")
    return page if isinstance(page, dict) else None


def _changed_preview_blocks(action, page):
    after_blocks = page.get("blocks") if isinstance(page.get("blocks"), list) else []
    before = action.before_snapshot if isinstance(action.before_snapshot, dict) else {}
    before_blocks = before.get("blocks") if isinstance(before.get("blocks"), list) else []
    before_map = {
        block_key(block, index): block for index, block in enumerate(before_blocks) if isinstance(block, dict)
    }
    changed_blocks = []
    for index, block in enumerate(after_blocks):
        if not isinstance(block, dict):
            continue
        key = block_key(block, index)
        if before_map.get(key) != block:
            changed_blocks.append(block)
    return changed_blocks


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
        parts.append(format_html('<div class="{}">{}</div>', css_class, mark_safe(sanitize_html(data["body_html"]))))
    return mark_safe("".join(str(part) for part in parts))


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
                mark_safe(sanitize_html(section.get("body_html", ""))),
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
            (
                item.get("question") or item.get("heading") or "Question",
                mark_safe(sanitize_html(item.get("answer", ""))),
            )
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
                    item.get("url", "#"),
                    item.get("title") or item.get("label") or item.get("url", "Link"),
                    format_html(" — {}", item.get("description", "")) if item.get("description") else "",
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
                (
                    format_html_join(
                        "",
                        "<td>{}</td>",
                        ((conditional_escape(cell),) for cell in row),
                    ),
                )
                for row in rows
                if isinstance(row, list)
            ),
        ),
    )


def _heading_level(value, default):
    try:
        level = int(value or default)
    except (TypeError, ValueError):
        level = default
    return min(max(level, 1), 6)
