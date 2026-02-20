import json

from django.test import TestCase, override_settings

FRONTEND_ORIGIN = "https://main.d27iyf1haq14j.amplifyapp.com"


@override_settings(
    CORS_ALLOWED_ORIGINS=[FRONTEND_ORIGIN],
    CORS_ALLOW_CREDENTIALS=True,
)
class HealthCheckCORSTest(TestCase):
    def test_health_returns_cors_for_allowed_origin(self):
        response = self.client.get("/health/", HTTP_ORIGIN=FRONTEND_ORIGIN)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("Access-Control-Allow-Origin"),
            FRONTEND_ORIGIN,
        )

    def test_health_omits_cors_for_unlisted_origin(self):
        response = self.client.get("/health/", HTTP_ORIGIN="https://not-allowed.example.com")

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.headers.get("Access-Control-Allow-Origin"))

    @override_settings(ALLOWED_HOSTS=["testserver"])
    def test_health_still_works_with_non_allowed_host(self):
        response = self.client.get("/health/", HTTP_HOST="not-allowed.example.com")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content), {"status": "ok"})
