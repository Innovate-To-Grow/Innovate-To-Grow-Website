from types import SimpleNamespace

from django.test import SimpleTestCase, override_settings
from django.urls import path
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.renderers import BROWSABLE_API_CACHE_CONTROL, BROWSABLE_API_ROBOTS, UCMercedBrowsableAPIRenderer


class RendererProbeView(APIView):
    permission_classes = [AllowAny]

    # noinspection PyMethodMayBeStatic
    def get(self, request):
        response = Response({"message": "probe"})
        response["Cache-Control"] = "public, max-age=60"
        response["ETag"] = '"json-validator"'
        return response


urlpatterns = [path("renderer-probe/", RendererProbeView.as_view())]


@override_settings(ROOT_URLCONF=__name__)
class UCMercedBrowsableAPIRendererTests(SimpleTestCase):
    def test_html_response_overrides_public_headers_and_omits_anonymous_csrf_cookie(self):
        response = self.client.get("/renderer-probe/", HTTP_ACCEPT="text/html")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], BROWSABLE_API_CACHE_CONTROL)
        self.assertEqual(response["X-Robots-Tag"], BROWSABLE_API_ROBOTS)
        self.assertNotIn("ETag", response)
        self.assertNotIn("csrftoken", response.cookies)
        self.assertNotIn(b"<style", response.content)

    def test_json_response_does_not_use_browsable_api_header_policy(self):
        response = self.client.get("/renderer-probe/", HTTP_ACCEPT="application/json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "public, max-age=60")
        self.assertEqual(response["ETag"], '"json-validator"')
        self.assertNotIn("X-Robots-Tag", response)

    def test_anonymous_read_only_detection_requires_both_conditions(self):
        anonymous_request = SimpleNamespace(user=SimpleNamespace(is_authenticated=False))
        authenticated_request = SimpleNamespace(user=SimpleNamespace(is_authenticated=True))
        read_only_view = SimpleNamespace(allowed_methods=["GET", "HEAD", "OPTIONS"])
        writable_view = SimpleNamespace(allowed_methods=["GET", "POST", "OPTIONS"])

        self.assertTrue(UCMercedBrowsableAPIRenderer._is_anonymous_read_only(anonymous_request, read_only_view))
        self.assertFalse(UCMercedBrowsableAPIRenderer._is_anonymous_read_only(authenticated_request, read_only_view))
        self.assertFalse(UCMercedBrowsableAPIRenderer._is_anonymous_read_only(anonymous_request, writable_view))
