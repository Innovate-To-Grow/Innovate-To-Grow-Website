from typing import Any

from django.core.exceptions import ValidationError

from cms.models import BLOCK_TYPE_CHOICES, CMSPage, validate_block_data
from cms.models.content.cms.cms_page import normalize_cms_route

from ..constants import CMS_PAGE_FIELDS
from ..exceptions import ActionRequestError
from ..utils import json_safe, validation_message
from .preview import normalize_cms_blocks


def find_cms_page(*, page_id: str | None = None, slug: str | None = None, route: str | None = None) -> CMSPage | None:
    qs = CMSPage.objects.prefetch_related("blocks")
    if page_id:
        return qs.filter(pk=page_id).first()
    if slug:
        return qs.filter(slug=slug).first()
    if route:
        return qs.filter(route=normalize_cms_route(route)).first()
    return None


def serialize_cms_page(page: CMSPage | None) -> dict[str, Any]:
    if page is None:
        return {}
    return {
        "slug": page.slug,
        "route": page.route,
        "title": page.title,
        "meta_description": page.meta_description,
        "page_css_class": page.page_css_class,
        "page_css": page.page_css,
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


def build_cms_page_proposal(page: CMSPage | None, page_fields: dict[str, Any], blocks: list[dict[str, Any]] | None):
    if not isinstance(page_fields, dict):
        raise ActionRequestError("page_fields must be an object.")
    unknown = sorted(set(page_fields) - CMS_PAGE_FIELDS)
    if unknown:
        raise ActionRequestError(f"Unsupported CMS page field: {unknown[0]}")
    proposed = serialize_cms_page(page) if page else {}
    proposed.update(page_fields)
    if blocks is not None:
        proposed["blocks"] = normalize_cms_blocks(blocks)
    elif "blocks" not in proposed:
        proposed["blocks"] = []
    validate_cms_page_payload(proposed, page)
    proposed["route"] = normalize_cms_route(proposed.get("route", ""))
    return json_safe(proposed)


def validate_cms_page_payload(payload: dict[str, Any], existing: CMSPage | None) -> None:
    for field in ("slug", "route", "title"):
        if not payload.get(field):
            raise ActionRequestError(f"CMS page field '{field}' is required.")
    payload["route"] = normalize_cms_route(payload.get("route", ""))
    if payload.get("status", "draft") not in {choice[0] for choice in CMSPage.STATUS_CHOICES}:
        raise ActionRequestError(f"Unsupported CMS page status: {payload.get('status')}")
    candidate = CMSPage.objects.get(pk=existing.pk) if existing else CMSPage()
    assign_cms_page_fields(candidate, payload)
    try:
        candidate.full_clean()
    except ValidationError as exc:
        raise ActionRequestError(validation_message(exc)) from exc
    validate_cms_blocks(payload.get("blocks") or [])


def validate_cms_blocks(blocks: list[dict[str, Any]]) -> None:
    block_types = {choice[0] for choice in BLOCK_TYPE_CHOICES}
    for index, block in enumerate(blocks):
        block_type = block.get("block_type", "")
        if block_type not in block_types:
            raise ActionRequestError(f"Block #{index + 1}: unknown type '{block_type}'.")
        try:
            validate_block_data(block_type, block.get("data", {}))
        except Exception as exc:
            raise ActionRequestError(f"Block #{index + 1} ({block_type}): {exc}") from exc


def assign_cms_page_fields(page: CMSPage, payload: dict[str, Any]) -> None:
    page.slug = payload.get("slug", "")
    page.route = normalize_cms_route(payload.get("route", ""))
    page.title = payload.get("title", "")
    page.meta_description = payload.get("meta_description", "")
    page.page_css_class = payload.get("page_css_class", "")
    page.page_css = payload.get("page_css", "")
    page.status = payload.get("status", "draft")
    page.sort_order = int(payload.get("sort_order") or 0)
