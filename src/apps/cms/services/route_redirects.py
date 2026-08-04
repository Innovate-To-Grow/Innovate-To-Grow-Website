"""Validation and conflict detection for public CMS routes and redirects."""

import re
from dataclasses import dataclass
from urllib.parse import unquote
from uuid import UUID

from django.core.exceptions import ValidationError

from apps.cms.app_routes import PROTECTED_APP_ROUTES, PUBLIC_APP_ROUTE_PATTERNS, PUBLIC_APP_ROUTES
from apps.cms.models.content.cms.cms_page import normalize_cms_route, validate_cms_route

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

URL_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
INVALID_PERCENT_ENCODING_RE = re.compile(r"%(?![0-9A-Fa-f]{2})")
LEGACY_ROUTE_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._~+-]+$")


@dataclass(frozen=True)
class RouteConflict:
    """A field-specific route conflict suitable for forms and JSON APIs."""

    code: str
    field: str
    message: str


def _matches_prefix(route: str, prefix: str) -> bool:
    folded_route = route.casefold()
    folded_prefix = prefix.casefold()
    return folded_route == folded_prefix or folded_route.startswith(f"{folded_prefix}/")


def _safe_uuid(value):
    if not value:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


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


def normalize_and_validate_cms_page_route(route: str | None) -> str:
    """Normalize a strict CMS page route, including editor slash cleanup."""

    raw_route = route or ""
    if any(ord(char) < 32 or ord(char) == 127 for char in raw_route):
        raise ValidationError("Paths cannot contain control characters.")
    if URL_SCHEME_RE.match(raw_route.strip()):
        raise ValidationError("Use a site-relative path, not a full URL.")
    if "?" in raw_route or "#" in raw_route:
        raise ValidationError("Paths cannot include a query string or fragment.")
    if "\\" in raw_route:
        raise ValidationError("Paths cannot contain backslashes.")
    return validate_cms_route(normalize_cms_route(raw_route))


def normalize_and_validate_route(route: str | None) -> str:
    """Normalize a strict redirect destination route."""

    raw_route = route or ""
    if raw_route.strip().startswith("//"):
        raise ValidationError("Protocol-relative paths are not allowed.")
    return normalize_and_validate_cms_page_route(raw_route)


def normalize_and_validate_legacy_source(route: str | None) -> str:
    """Normalize a safe legacy path while allowing common URL punctuation."""

    raw_route = route or ""
    trimmed = raw_route.strip()
    if any(ord(char) < 32 or ord(char) == 127 for char in raw_route):
        raise ValidationError("Paths cannot contain control characters.")
    if URL_SCHEME_RE.match(trimmed):
        raise ValidationError("Use a site-relative path, not a full URL.")
    if trimmed.startswith("//"):
        raise ValidationError("Protocol-relative paths are not allowed.")
    if "?" in trimmed or "#" in trimmed:
        raise ValidationError("Paths cannot include a query string or fragment.")
    if "\\" in trimmed:
        raise ValidationError("Paths cannot contain backslashes.")

    segments: list[str] = []
    for encoded_segment in (segment for segment in trimmed.split("/") if segment):
        if INVALID_PERCENT_ENCODING_RE.search(encoded_segment):
            raise ValidationError("Path contains invalid percent encoding.")
        try:
            segment = unquote(encoded_segment, errors="strict")
        except UnicodeDecodeError:
            raise ValidationError("Path contains invalid percent encoding.")
        if segment in {".", ".."}:
            raise ValidationError("Dot path segments are not allowed.")
        if "/" in segment or "\\" in segment:
            raise ValidationError("Encoded slash or backslash characters are not allowed.")
        if any(ord(char) < 32 or ord(char) == 127 for char in segment):
            raise ValidationError("Paths cannot contain control characters.")
        if not LEGACY_ROUTE_SEGMENT_RE.fullmatch(segment):
            raise ValidationError(
                "Legacy path segments may use letters, numbers, dots, hyphens, underscores, tildes, or plus signs."
            )
        segments.append(segment)

    return "/" + "/".join(segments) if segments else "/"


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

    conflicts: list[RouteConflict] = []
    if normalized == "/" and not allow_root:
        conflicts.append(
            RouteConflict(
                "root_redirect_source",
                "source_path",
                "The site root cannot be used as a redirect source.",
            )
        )
    reserved = next((prefix for prefix in RESERVED_ROUTE_PREFIXES if _matches_prefix(normalized, prefix)), None)
    if reserved:
        conflicts.append(
            RouteConflict(
                "reserved_route",
                "source_path",
                f'Path "{normalized}" is reserved for system route "{reserved}".',
            )
        )

    app_route = match_public_app_route(normalized)
    if app_route:
        conflicts.append(
            RouteConflict(
                "application_route",
                "source_path",
                f'Path "{normalized}" is owned by application route "{app_route}".',
            )
        )

    # Local imports keep model import order acyclic: RouteRedirect.clean() uses
    # this service after Django has finished constructing the model classes.
    from apps.cms.models import CMSPage, RouteRedirect

    page_qs = CMSPage.objects.filter(route=normalized)
    page_id = _safe_uuid(exclude_page_id)
    if page_id:
        page_qs = page_qs.exclude(pk=page_id)
    page = page_qs.only("title", "status").first()
    if page:
        conflicts.append(
            RouteConflict(
                "cms_page",
                "source_path",
                f'Path "{normalized}" is already used by "{page.title}" ({page.status}).',
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

    from apps.cms.models import CMSPage, RouteRedirect

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
