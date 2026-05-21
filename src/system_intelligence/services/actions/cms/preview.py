from collections.abc import Iterable
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from cms.models import CMSBlock, CMSPage
from cms.models.content.cms.cms_page import normalize_cms_route

from ..constants import PREVIEW_TTL_SECONDS


def normalize_cms_blocks(blocks: list[dict]) -> list[dict]:
    if not isinstance(blocks, list):
        from ..exceptions import ActionRequestError

        raise ActionRequestError("blocks must be a list.")
    normalized = []
    for index, block in enumerate(blocks):
        if not isinstance(block, dict):
            from ..exceptions import ActionRequestError

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
    for index, block in enumerate(blocks):
        CMSBlock.objects.create(
            page=page,
            block_type=block.get("block_type"),
            sort_order=index,
            admin_label=block.get("admin_label", ""),
            data=block.get("data") or {},
        )


def store_cms_preview(data: dict) -> tuple[str, str, timezone.datetime]:
    import uuid

    token = uuid.uuid4().hex
    expires_at = timezone.now() + timedelta(seconds=PREVIEW_TTL_SECONDS)
    preview_data = dict(data)
    preview_data["expires_at"] = expires_at.isoformat()
    cache.set(f"cms:preview:{token}", preview_data, timeout=PREVIEW_TTL_SECONDS)
    return token, build_preview_url(preview_data.get("route", "/"), token), expires_at


def build_preview_url(route: str, token: str) -> str:
    base = (getattr(settings, "FRONTEND_URL", "") or "").rstrip("/")
    route = normalize_cms_route(route)
    path = f"{base}{route}" if base else route
    return f"{path}?{urlencode({'cms_preview_token': token})}"


def clear_cms_cache(old_route: str, new_route: str, preview_token: str) -> None:
    if old_route:
        cache.delete(f"cms:page:{old_route}")
    cache.delete(f"cms:page:{new_route}")
    if preview_token:
        cache.delete(f"cms:preview:{preview_token}")
