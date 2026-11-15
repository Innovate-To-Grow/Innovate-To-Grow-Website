"""Mountable URL patterns for the Legacy viewer gateway."""

from django.urls import path

from .views import legacy_access_exchange_gateway, legacy_proxy_view

app_name = "legacy_view"

urlpatterns = [
    path("_i2g-auth/exchange", legacy_access_exchange_gateway, name="exchange"),
    path("", legacy_proxy_view, {"legacy_path": ""}, name="root"),
    path("<path:legacy_path>", legacy_proxy_view, name="proxy"),
]


def get_legacy_view_urls():
    """Return patterns so the project URLConf can mount them without app imports."""

    return urlpatterns
