"""Validation and conflict detection for public CMS routes and redirects."""

from django.core.exceptions import ValidationError

from apps.cms.app_routes import PROTECTED_APP_ROUTES, PUBLIC_APP_ROUTE_PATTERNS, PUBLIC_APP_ROUTES
from apps.cms.models.content.cms.cms_page import normalize_cms_route
from apps.cms.services.routing.route_conflict_checks import RouteConflict, _owner_conflicts, _redirect_chain_conflicts
from apps.cms.services.routing.route_validation import (
    normalize_and_validate_cms_page_route,
    normalize_and_validate_legacy_source,
    normalize_and_validate_route,
)

# These paths are handled before the public React/CMS router.  A route is
# reserved when it equals a prefix or starts with that prefix plus ``/``.
RESERVED_ROUTE_PREFIXES = (
    "/api",
    "/admin",
    "/admin-api",
    "/static",
    "/media",
    "/assets",
    "/health",
    "/livez",
    "/readyz",
    "/maintenance",
    "/csp-report",
    "/robots.txt",
    "/sitemap.xml",
    "/index.html",
    "/favicon.ico",
    "/.well-known",
    *PROTECTED_APP_ROUTES,
)


def _matches_prefix(route: str, prefix: str) -> bool:
    folded_route = route.casefold()
    folded_prefix = prefix.casefold()
    return folded_route == folded_prefix or folded_route.startswith(f"{folded_prefix}/")


def match_fixed_public_app_route(route: str) -> str | None:
    """Return the canonical fixed React route matching ``route``."""
    fixed_routes = {entry["url"].casefold(): entry["url"] for entry in PUBLIC_APP_ROUTES}
    return fixed_routes.get(route.casefold())


def match_public_app_route(route: str) -> str | None:
    """Return the matching fixed route/pattern, if React owns ``route``."""

    fixed_route = match_fixed_public_app_route(route)
    if fixed_route:
        return fixed_route

    route_segments = route.strip("/").split("/") if route != "/" else []
    for pattern in PUBLIC_APP_ROUTE_PATTERNS:
        pattern_segments = pattern.strip("/").split("/")
        if len(route_segments) != len(pattern_segments):
            continue
        if all(
            bool(route_segment)
            and (pattern_segment.startswith(":") or pattern_segment.casefold() == route_segment.casefold())
            for route_segment, pattern_segment in zip(route_segments, pattern_segments, strict=True)
        ):
            return pattern
    return None


def _reserved_route_conflicts(normalized: str, *, allow_root: bool) -> list[RouteConflict]:
    """The root, system prefixes and public application routes cannot be taken over."""
    conflicts: list[RouteConflict] = []
    if normalized == "/" and not allow_root:
        conflicts.append(
            RouteConflict("root_redirect_source", "source_path", "The site root cannot be used as a redirect source.")
        )
    reserved = next((prefix for prefix in RESERVED_ROUTE_PREFIXES if _matches_prefix(normalized, prefix)), None)
    if reserved:
        conflicts.append(
            RouteConflict(
                "reserved_route", "source_path", f'Path "{normalized}" is reserved for system route "{reserved}".'
            )
        )
    app_route = match_public_app_route(normalized)
    if app_route:
        conflicts.append(
            RouteConflict(
                "application_route", "source_path", f'Path "{normalized}" is owned by application route "{app_route}".'
            )
        )
    return conflicts


def source_route_conflicts(
    route: str | None,
    *,
    exclude_page_id=None,
    exclude_redirect_id=None,
    allow_root=False,
    allow_legacy_syntax=False,
) -> tuple[str, list[RouteConflict]]:
    """Return normalized route plus every conflict that prevents route ownership."""

    try:
        validator = (
            normalize_and_validate_legacy_source if allow_legacy_syntax else normalize_and_validate_cms_page_route
        )
        normalized = validator(route)
    except ValidationError as exc:
        return normalize_cms_route(route), [RouteConflict("invalid", "source_path", exc.messages[0])]

    conflicts = _reserved_route_conflicts(normalized, allow_root=allow_root)
    conflicts.extend(
        _owner_conflicts(normalized, exclude_page_id=exclude_page_id, exclude_redirect_id=exclude_redirect_id)
    )
    return normalized, conflicts


def redirect_mapping_conflicts(
    source_path: str | None,
    destination_path: str | None,
    *,
    exclude_redirect_id=None,
) -> tuple[str, str, list[RouteConflict]]:
    """Validate a redirect mapping and return normalized paths plus conflicts."""

    source, conflicts = source_route_conflicts(
        source_path,
        exclude_redirect_id=exclude_redirect_id,
        allow_legacy_syntax=True,
    )
    try:
        destination = normalize_and_validate_route(destination_path)
    except ValidationError as exc:
        destination = normalize_cms_route(destination_path)
        conflicts.append(RouteConflict("invalid", "destination_path", exc.messages[0]))
        return source, destination, conflicts

    if source == destination:
        conflicts.append(
            RouteConflict(
                "self_redirect",
                "destination_path",
                "Source and destination resolve to the same path.",
            )
        )

    conflicts.extend(_redirect_chain_conflicts(source, destination, exclude_redirect_id=exclude_redirect_id))

    from apps.cms.models import CMSPage

    published_page_exists = CMSPage.objects.filter(route=destination, status="published").exists()
    # Dynamic application paths may still 404 for an unknown object ID. Only
    # fixed registered routes are safe redirect destinations; dynamic patterns
    # remain reserved as sources so React ownership cannot be shadowed.
    app_route = match_fixed_public_app_route(destination)
    if not published_page_exists and not app_route and destination != "/":
        conflicts.append(
            RouteConflict(
                "missing_destination",
                "destination_path",
                f'Destination "{destination}" must be a published CMS page or public application route.',
            )
        )

    return source, destination, conflicts


def page_route_conflicts(route: str | None, *, exclude_page_id=None) -> tuple[str, list[RouteConflict]]:
    """Validate a CMS page route against all other route owners."""

    normalized, conflicts = source_route_conflicts(
        route,
        exclude_page_id=exclude_page_id,
        allow_root=True,
    )
    # CMS page forms call this helper, so present errors against their ``route``
    # field rather than the redirect model's ``source_path`` field.
    return normalized, [RouteConflict(item.code, "route", item.message) for item in conflicts]


def destination_route_choices() -> list[tuple[str, list[tuple[str, str]]]]:
    """Return grouped select choices for published CMS and fixed app routes."""

    from apps.cms.models import CMSPage

    cms_choices = [
        (route, f"{title} ({route})")
        for route, title in CMSPage.objects.filter(status="published")
        .order_by("title", "route")
        .values_list("route", "title")
    ]
    app_choices = [("/", "Homepage (/)")]
    app_choices.extend((entry["url"], f"{entry['title']} ({entry['url']})") for entry in PUBLIC_APP_ROUTES)
    return [("Published CMS pages", cms_choices), ("Application routes", app_choices)]
