from typing import Any

from django.db import transaction

from cms.models import CMSBlock, CMSPage
from core.models.base.system_intelligence import SystemIntelligenceActionRequest
from core.services.db_tools.helpers import _truncate

from .cms_helpers import (
    assign_cms_page_fields,
    build_cms_page_proposal,
    find_cms_page,
    serialize_cms_page,
    validate_cms_page_payload,
)
from .cms_preview import clear_cms_cache, create_cms_blocks, store_cms_preview
from .comparison import build_cms_comparison, build_diff
from .context import current_conversation, current_user_id
from .exceptions import ActionRequestError
from .orm_records import assert_snapshot_unchanged
from .serialization import proposal_tool_response


def get_cms_page_detail(page_id: str | None = None, slug: str | None = None, route: str | None = None) -> str:
    """Return CMS page fields and blocks for a page targeted by ID, slug, or route."""
    page = find_cms_page(page_id=page_id, slug=slug, route=route)
    if page is None:
        raise ActionRequestError("CMS page not found.")
    import json

    from django.core.serializers.json import DjangoJSONEncoder

    return _truncate(json.dumps(serialize_cms_page(page), indent=2, cls=DjangoJSONEncoder))


def propose_cms_page_update(
    page_id: str | None = None,
    slug: str | None = None,
    route: str | None = None,
    page_fields: dict[str, Any] | None = None,
    blocks: list[dict[str, Any]] | None = None,
    summary: str | None = None,
) -> dict[str, Any]:
    """Create a pending CMS page update action and cached preview."""
    conversation = current_conversation()
    page = find_cms_page(page_id=page_id, slug=slug, route=route)
    before = serialize_cms_page(page) if page else {}
    proposed = build_cms_page_proposal(page, page_fields or {}, blocks)
    preview_token, preview_url, expires_at = store_cms_preview(proposed)
    comparison = build_cms_comparison(before, proposed)
    action = SystemIntelligenceActionRequest.objects.create(
        conversation=conversation,
        created_by_id=current_user_id(),
        action_type=SystemIntelligenceActionRequest.ACTION_CMS_PAGE_UPDATE,
        target_app_label="cms",
        target_model="CMSPage",
        target_pk=str(page.pk) if page else "",
        target_repr=page.title if page else proposed.get("title", "New CMS page"),
        title=f"Update CMS page: {proposed.get('title', proposed.get('route', 'Untitled'))}",
        summary=summary or "Review the generated CMS page preview before applying this change.",
        payload={"page": proposed, "comparison": comparison},
        before_snapshot=before,
        after_snapshot=proposed,
        diff=build_diff(before, proposed),
        preview_token=preview_token,
        preview_url=preview_url,
        preview_expires_at=expires_at,
    )
    return proposal_tool_response(action, "CMS page change is ready for review. Open the preview before approving.")


def apply_cms_page_update(action: SystemIntelligenceActionRequest) -> None:
    proposed = action.payload.get("page")
    if not isinstance(proposed, dict):
        raise ActionRequestError("Invalid CMS page action payload.")
    page = CMSPage.objects.prefetch_related("blocks").filter(pk=action.target_pk).first() if action.target_pk else None
    if page is not None:
        assert_snapshot_unchanged(action.before_snapshot, serialize_cms_page(page), "CMS page")
    validate_cms_page_payload(proposed, page)
    old_route = page.route if page else ""
    page = page or CMSPage()
    assign_cms_page_fields(page, proposed)
    page.full_clean()
    page.save()
    CMSBlock.objects.filter(page=page).delete()
    create_cms_blocks(page, proposed.get("blocks", []))
    action.target_pk = str(page.pk)
    action.target_repr = page.title
    transaction.on_commit(lambda: clear_cms_cache(old_route, page.route, action.preview_token))
