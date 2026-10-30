"""System-level public views: robots.txt, landing page, error handlers. The sitemap is CMS content (``apps.cms.views.sitemap``)."""

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render

# The site's pages are rendered in the browser from this API, so a search engine renders them only if robots.txt
# lets it fetch the public reads they make. Crawlers apply the longest matching rule (an Allow wins a tie), so
# these open what the public pages read and the final Disallow keeps everything else out.
_ROBOTS_ALLOWED_READS = (
    "/health/",
    "/layout/",
    "/cms/pages/",
    "/cms/homepage/",
    "/cms/embed/",
    "/news/",
    "/event/schedule/",
    "/projects/",
    "/media/",
    "/static/",
)
# Under /projects/, only the archive and project details render public pages.
_ROBOTS_DISALLOWED_READS = (
    "/projects/past-shares/",
    "/projects/past-ai-search/",
    "/projects/past-all/",
    "/projects/past/",
)


def robots_txt(request):
    """Serve robots.txt for search engine crawlers: the public page reads are allowed, nothing else."""
    lines = [
        "User-agent: *",
        *(f"Allow: {path}" for path in _ROBOTS_ALLOWED_READS),
        *(f"Disallow: {path}" for path in _ROBOTS_DISALLOWED_READS),
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
