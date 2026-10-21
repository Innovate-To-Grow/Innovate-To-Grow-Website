"""System-level public views: robots.txt, landing page, error handlers. The sitemap is CMS content (``apps.cms.views.sitemap``)."""

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render


def robots_txt(request):
    """Serve robots.txt for search engine crawlers."""
    lines = [
        "User-agent: *",
        "Disallow: /",
        "",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")


def root_index(request):
    """Static landing page"""

    return render(request, "index.html", status=200)


# Paths whose 404 is a page a person reads in the browser; every other path is an API client's.
_HTML_404_PREFIXES = ("/admin/", "/legacy-view/")


# noinspection PyUnusedLocal
def custom_404(request, exception):
    """404 for unknown paths: the admin-themed page inside the admin, JSON like DRF's everywhere else."""
    if request.path.startswith(_HTML_404_PREFIXES):
        return render(request, "404.html", status=404)
    return JsonResponse({"detail": "Not found."}, status=404)
