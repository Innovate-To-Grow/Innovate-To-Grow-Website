"""URL registration helper for ``CoreConfig.ready()``."""

from functools import wraps

from django.contrib import admin
from django.urls import path

from .views import infrastructure_status_data_view, infrastructure_status_view


def _bind_admin_site(view, site):
    @wraps(view)
    def bound(request, *args, **kwargs):
        return view(request, *args, admin_site=site, **kwargs)

    return bound


def get_infrastructure_status_urls(admin_site=None):
    """Return the custom URL list, wrapped by the supplied admin site.

    ``CoreConfig.ready()`` can prepend this list to the prior
    ``AdminSite.get_urls`` result. Accepting the site instance keeps the helper
    correct for alternate AdminSite instances used by tests.
    """

    site = admin_site or admin.site
    return [
        path(
            "status/infrastructure/",
            site.admin_view(_bind_admin_site(infrastructure_status_view, site)),
            name="core_infrastructure_status",
        ),
        path(
            "status/infrastructure/data/",
            site.admin_view(_bind_admin_site(infrastructure_status_data_view, site)),
            name="core_infrastructure_status_data",
        ),
    ]
