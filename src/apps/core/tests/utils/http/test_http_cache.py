from django.test import RequestFactory, SimpleTestCase

from apps.core.utils.http_cache import public_json_response


class PublicJsonResponseTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.data = {"message": "public"}

    def test_returns_public_cache_headers(self):
        response = public_json_response(self.factory.get("/public/"), self.data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "public, max-age=60, stale-while-revalidate=300")
        self.assertTrue(response["ETag"].startswith('"'))

    def test_weak_comma_separated_validator_returns_empty_304(self):
        etag = public_json_response(self.factory.get("/public/"), self.data)["ETag"]
        request = self.factory.get("/public/", HTTP_IF_NONE_MATCH=f'"different", W/{etag}')

        response = public_json_response(request, self.data)

        self.assertEqual(response.status_code, 304)
        self.assertEqual(response.content, b"")
        self.assertEqual(response["ETag"], etag)
        self.assertIn("public", response["Cache-Control"])

    def test_wildcard_validator_returns_304(self):
        response = public_json_response(self.factory.get("/public/", HTTP_IF_NONE_MATCH="*"), self.data)

        self.assertEqual(response.status_code, 304)
        self.assertEqual(response.content, b"")

    def test_non_matching_validator_returns_200(self):
        response = public_json_response(self.factory.get("/public/", HTTP_IF_NONE_MATCH='"different"'), self.data)

        self.assertEqual(response.status_code, 200)
