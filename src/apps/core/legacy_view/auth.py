"""Single integration point with the Legacy viewer grant/session service."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse


def require_legacy_viewer(request: HttpRequest):
    """Return the authorized user or propagate LegacyViewerAccessDenied."""

    from apps.core.services.legacy_access import require_legacy_viewer as require_viewer

    return require_viewer(request)


def is_legacy_viewer_access_denied(exception: Exception) -> bool:
    from apps.core.services.legacy_access import LegacyViewerAccessDenied

    return isinstance(exception, LegacyViewerAccessDenied)


def clear_legacy_viewer_cookie(response: HttpResponse) -> HttpResponse:
    from apps.core.services.legacy_access import clear_legacy_viewer_cookie as clear_cookie

    clear_cookie(response)
    return response
