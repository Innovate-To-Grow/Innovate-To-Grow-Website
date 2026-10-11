"""URL registration helper for the legacy-viewer Admin page."""

from functools import wraps

from django.contrib import admin
from django.urls import path

from .views import legacy_view_launch


def _bind_admin_site(view, site):
    @wraps(view)
    def bound(request, *args, **kwargs):
        return view(request, *args, admin_site=site, **kwargs)

    return bound


def get_legacy_view_admin_urls(admin_site=None):
    """Return the custom ``/admin/legacy-view/`` URL for an AdminSite."""

    site = admin_site or admin.site
    return [
        path(
            "legacy-view/",
            site.admin_view(_bind_admin_site(legacy_view_launch, site)),
            name="core_legacy_view_launch",
        )
    ]
