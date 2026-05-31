"""Serve a frozen page's captured HTML for embedding in a sandboxed iframe."""

from __future__ import annotations

from django.conf import settings
from django.core.cache import cache
from django.http import Http404, HttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.clickjacking import xframe_options_exempt

from apps.cms.models import FrozenPage

# Static part of the policy: the document inlines everything as data: URIs and
# contains no scripts, so we lock it to data: assets + inline styles only. With no
# script-src (under default-src 'none') scripts can't run even if one slipped past
# the capture-time stripper. The frame-ancestors directive is appended per-request
# (see _frozen_csp) so the cross-origin production frontend can frame it.
FROZEN_CSP_BASE = "default-src 'none'; img-src data:; font-src data:; media-src data:; style-src 'unsafe-inline' data:"

_CACHE_TTL = 300


def _frozen_csp() -> str:
    """CSP allowing our own origin plus the configured frontend origin to frame the document.

    The public site is served from a different origin than Django in production
    (Amplify/CloudFront frontend, separate API host), so 'self' alone would block
    the iframe. We add FRONTEND_URL when configured. frame-ancestors is the modern
    replacement for X-Frame-Options and is the only framing control we set — the
    view is xframe_options_exempt so no conflicting X-Frame-Options header remains.
    """
    ancestors = ["'self'"]
    frontend = (getattr(settings, "FRONTEND_URL", "") or "").rstrip("/")
    if frontend:
        ancestors.append(frontend)
    return f"{FROZEN_CSP_BASE}; frame-ancestors {' '.join(ancestors)}"


def frozen_page_cache_key(pk) -> str:
    return f"cms:frozen:{pk}"


def clear_frozen_page_cache(pk) -> None:
    cache.delete(frozen_page_cache_key(pk))


def _document_response(html: str) -> HttpResponse:
    resp = HttpResponse(html, content_type="text/html; charset=utf-8")
    resp["Content-Security-Policy"] = _frozen_csp()
    resp["Referrer-Policy"] = "no-referrer"
    return resp


@method_decorator(xframe_options_exempt, name="dispatch")
class FrozenPageDocumentView(View):
    """Raw HTML document for a single frozen page, shown inside a sandboxed iframe.

    ``xframe_options_exempt`` is required because the project sets
    ``X_FRAME_OPTIONS = "DENY"`` globally; stripping it lets CSP frame-ancestors
    be the single (cross-origin-capable) framing control.
    """

    def get(self, request, pk):
        cache_key = frozen_page_cache_key(pk)
        cached = cache.get(cache_key)
        if cached is not None:
            return _document_response(cached)

        frozen = FrozenPage.objects.filter(pk=pk).first()
        if frozen is None:
            raise Http404("Frozen page not found")

        if frozen.is_visible():
            cache.set(cache_key, frozen.frozen_html, _CACHE_TTL)
            return _document_response(frozen.frozen_html)

        # Draft / not-yet-captured: staff-only preview, never cached.
        if request.user.is_authenticated and request.user.is_staff and frozen.frozen_html:
            return _document_response(frozen.frozen_html)

        raise Http404("Frozen page not found")
