from typing import Any

from ..query_helpers import bounded_limit
from ..runtime import run_action_service_async


async def search_cms_assets(name: str | None = None, limit: int | None = None) -> dict[str, Any]:
    """Search reusable CMS assets by name."""
    return await run_action_service_async(_search_cms_assets, name, limit)


def _search_cms_assets(name=None, limit=None) -> dict[str, Any]:
    from cms.models import CMSAsset

    qs = CMSAsset.objects.all()
    if name:
        qs = qs.filter(name__icontains=name)
    rows = []
    for asset in qs.order_by("name", "-created_at")[: bounded_limit(limit)]:
        rows.append(
            {
                "id": str(asset.id),
                "name": asset.name,
                "public_url": asset.public_url,
                "created_at": asset.created_at.isoformat() if asset.created_at else None,
                "updated_at": asset.updated_at.isoformat() if asset.updated_at else None,
            }
        )
    return {"shown": len(rows), "total": qs.count(), "rows": rows}
