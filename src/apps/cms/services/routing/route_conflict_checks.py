from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class RouteConflict:
    """A field-specific route conflict suitable for forms and JSON APIs."""

    code: str
    field: str
    message: str


def _safe_uuid(value):
    if not value:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _owner_conflicts(normalized: str, *, exclude_page_id, exclude_redirect_id) -> list[RouteConflict]:
    """A CMS page or another redirect that already owns ``normalized``."""
    # Local imports keep model import order acyclic: RouteRedirect.clean() uses
    # this service after Django has finished constructing the model classes.
    from apps.cms.models import CMSPage, RouteRedirect

    conflicts: list[RouteConflict] = []
    page_qs = CMSPage.objects.filter(route=normalized)
    page_id = _safe_uuid(exclude_page_id)
    if page_id:
        page_qs = page_qs.exclude(pk=page_id)
    page = page_qs.only("title", "status").first()
    if page:
        conflicts.append(
            RouteConflict(
                "cms_page", "source_path", f'Path "{normalized}" is already used by "{page.title}" ({page.status}).'
            )
        )

    redirect_qs = RouteRedirect.objects.filter(source_path=normalized)
    redirect_id = _safe_uuid(exclude_redirect_id)
    if redirect_id:
        redirect_qs = redirect_qs.exclude(pk=redirect_id)
    redirect = redirect_qs.only("destination_path", "is_active").first()
    if redirect:
        state = "active" if redirect.is_active else "inactive"
        conflicts.append(
            RouteConflict(
                "redirect_source",
                "source_path",
                f'Path "{normalized}" is already a {state} redirect to "{redirect.destination_path}".',
            )
        )
    return conflicts


def _redirect_chain_conflicts(source: str, destination: str, *, exclude_redirect_id) -> list[RouteConflict]:
    """Redirects may not chain or cycle: the destination is no redirect source, nothing points at the source."""
    from apps.cms.models import RouteRedirect

    conflicts: list[RouteConflict] = []
    destination_redirects = RouteRedirect.objects.filter(source_path=destination)
    inbound_redirects = RouteRedirect.objects.filter(destination_path=source)
    redirect_id = _safe_uuid(exclude_redirect_id)
    if redirect_id:
        destination_redirects = destination_redirects.exclude(pk=redirect_id)
        inbound_redirects = inbound_redirects.exclude(pk=redirect_id)

    destination_redirect = destination_redirects.only("destination_path").first()
    if destination_redirect:
        code = "redirect_cycle" if destination_redirect.destination_path == source else "redirect_chain"
        message = (
            f'Redirect would create a cycle through "{destination}".'
            if code == "redirect_cycle"
            else f'Destination "{destination}" is itself a redirect source; redirect chains are not allowed.'
        )
        conflicts.append(RouteConflict(code, "destination_path", message))

    inbound_redirect = inbound_redirects.only("source_path").first()
    if inbound_redirect:
        conflicts.append(
            RouteConflict(
                "redirect_chain",
                "source_path",
                f'Source "{source}" is already the destination of redirect "{inbound_redirect.source_path}".',
            )
        )
    return conflicts
