from django.test import SimpleTestCase, override_settings
from django.urls import include, path, resolve

from apps.core.legacy_view import get_legacy_view_urls
from apps.core.legacy_view.views import legacy_access_exchange_gateway, legacy_proxy_view

urlpatterns = [path("legacy-view/", include(get_legacy_view_urls()))]


@override_settings(ROOT_URLCONF=__name__)
class LegacyViewURLTest(SimpleTestCase):
    def test_mountable_patterns_route_exchange_before_proxy(self):
        self.assertIs(resolve("/legacy-view/_i2g-auth/exchange").func, legacy_access_exchange_gateway)
        self.assertIs(resolve("/legacy-view/").func, legacy_proxy_view)
        self.assertIs(resolve("/legacy-view/static/images/logo.png").func, legacy_proxy_view)

    def test_proxy_receives_only_the_legacy_subpath(self):
        match = resolve("/legacy-view/past-projects/123e4567-e89b-12d3-a456-426614174000")
        self.assertEqual(match.kwargs["legacy_path"], "past-projects/123e4567-e89b-12d3-a456-426614174000")
