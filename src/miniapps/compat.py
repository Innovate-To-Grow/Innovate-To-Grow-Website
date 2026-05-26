"""Backward-compatibility bridge for APP_ROUTES consumers.

Merges DB-managed MiniApp records with the legacy hardcoded list.
"""

import logging

logger = logging.getLogger(__name__)


def get_all_app_routes():
    """Return combined list of legacy hardcoded + DB-managed app routes.

    Used by: menu editor, embed widget admin, login redirects.
    Falls back to legacy-only if DB is unavailable (e.g. during migrations).
    """
    from cms.app_routes import _LEGACY_APP_ROUTES

    try:
        from miniapps.models import MiniApp

        db_routes = list(
            MiniApp.objects.filter(status="published").values("url_path", "title", "embeddable").order_by("title")
        )
    except Exception:
        logger.debug("miniapps table not available, using legacy routes only")
        return list(_LEGACY_APP_ROUTES)

    seen = set()
    combined = []

    for r in _LEGACY_APP_ROUTES:
        combined.append(r)
        seen.add(r["url"])

    for r in db_routes:
        url = r["url_path"]
        if url not in seen:
            combined.append({"url": url, "title": r["title"], "embeddable": r["embeddable"]})
            seen.add(url)

    return combined


def get_embeddable_app_routes():
    """Return only embeddable routes from the combined list."""
    return [r for r in get_all_app_routes() if r.get("embeddable")]
