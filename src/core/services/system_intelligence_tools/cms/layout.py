from typing import Any

from core.services.system_intelligence_actions.exceptions import ActionRequestError

from ..query_helpers import object_payload, queryset_payload, require_one
from ..runtime import run_action_service_async


async def search_menus(
    name: str | None = None, is_active: bool | None = None, limit: int | None = None
) -> dict[str, Any]:
    """Search layout menus by name or active state."""
    return await run_action_service_async(_search_menus, name, is_active, limit)


async def get_menu_detail(menu_id: str | None = None, name: str | None = None) -> dict[str, Any]:
    """Get a layout menu including its JSON items."""
    return await run_action_service_async(_get_menu_detail, menu_id, name)


async def get_footer_content_detail(
    footer_id: str | None = None, slug: str | None = None, active_only: bool | None = True
) -> dict[str, Any]:
    """Get footer content JSON by id, slug, or the active footer."""
    return await run_action_service_async(_get_footer_content_detail, footer_id, slug, active_only)


async def get_site_settings_detail() -> dict[str, Any]:
    """Get site settings including homepage route and design-token groups."""
    return await run_action_service_async(_get_site_settings_detail)


def _search_menus(name=None, is_active=None, limit=None) -> dict[str, Any]:
    from cms.models import Menu

    qs = Menu.objects.all()
    if name:
        qs = qs.filter(name__icontains=name)
    if is_active is not None:
        qs = qs.filter(is_active=is_active)
    return queryset_payload(qs.order_by("name"), ["id", "name", "display_name", "is_active", "updated_at"], limit=limit)


def _find_menu(menu_id=None, name=None):
    from cms.models import Menu

    qs = Menu.objects.all()
    if menu_id:
        return require_one(qs.filter(pk=menu_id), "Menu")
    if name:
        return require_one(qs.filter(name__icontains=name), "Menu")
    raise ActionRequestError("Provide menu_id or name.")


def _get_menu_detail(menu_id=None, name=None) -> dict[str, Any]:
    menu = _find_menu(menu_id, name)
    return {
        "menu": object_payload(menu, ["id", "name", "display_name", "description", "items", "is_active", "updated_at"])
    }


def _get_footer_content_detail(footer_id=None, slug=None, active_only=True) -> dict[str, Any]:
    from cms.models import FooterContent

    qs = FooterContent.objects.all()
    if footer_id:
        footer = require_one(qs.filter(pk=footer_id), "Footer content")
    elif slug:
        footer = require_one(qs.filter(slug=slug), "Footer content")
    elif active_only:
        footer = require_one(qs.filter(is_active=True), "Active footer content")
    else:
        footer = require_one(qs.order_by("-updated_at"), "Footer content")
    return {"footer": object_payload(footer, ["id", "name", "slug", "content", "is_active", "updated_at"])}


def _get_site_settings_detail() -> dict[str, Any]:
    from cms.models import SiteSettings

    settings = SiteSettings.load()
    tokens = settings.design_tokens or {}
    return {
        "site_settings": object_payload(settings, ["id", "homepage_page_id", "design_tokens"]),
        "homepage_route": settings.get_homepage_route(),
        "design_token_groups": sorted(tokens.keys()) if isinstance(tokens, dict) else [],
    }
