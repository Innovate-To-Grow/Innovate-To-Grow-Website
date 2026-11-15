import re

from django.core.exceptions import ValidationError

ROUTE_SEGMENT_RE = re.compile(r"^[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*$")


def normalize_cms_route(route):
    """Normalize CMS route paths to a canonical leading-slash/no-trailing-slash form."""
    route = (route or "").strip()
    if not route:
        return "/"

    segments = [segment.strip() for segment in route.split("/") if segment.strip()]
    if not segments:
        return "/"

    return "/" + "/".join(segments)


def validate_cms_route(route):
    """Validate a normalized CMS route."""
    normalized = normalize_cms_route(route)

    if normalized == "/":
        return normalized

    for segment in normalized.strip("/").split("/"):
        if not ROUTE_SEGMENT_RE.fullmatch(segment):
            raise ValidationError(
                "Each path segment must use letters, numbers, hyphens, or underscores only.",
            )

    return normalized
