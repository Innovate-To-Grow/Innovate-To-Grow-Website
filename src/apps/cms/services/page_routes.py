"""Transactional CMS page route-change operations."""

from apps.cms.models import RouteRedirect


def apply_page_route_change(*, page, old_route: str, keep_redirect: bool) -> None:
    """Retarget inbound mappings and optionally preserve a page's old URL."""

    if old_route == page.route:
        return

    # The CMSPage save path already holds the shared route/page locks. Keep
    # redirect row acquisition deterministic for nested admin rename flows.
    inbound_redirects = list(
        RouteRedirect.objects.select_for_update().filter(destination_path=old_route).order_by("source_path", "pk")
    )
    for redirect in inbound_redirects:
        redirect.destination_path = page.route
        redirect.save(update_fields=["destination_path", "updated_at"])

    if keep_redirect:
        RouteRedirect.objects.create(
            source_path=old_route,
            destination_path=page.route,
            is_active=True,
            notes=f'Automatically created when CMS page "{page.title}" changed routes.',
        )
