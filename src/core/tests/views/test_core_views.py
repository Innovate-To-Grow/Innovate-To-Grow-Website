from django.test import RequestFactory, TestCase

from core.views import custom_404


class RobotsTxtTest(TestCase):
    def test_returns_text_plain(self):
        response = self.client.get("/robots.txt")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/plain")

    def test_disallows_all(self):
        response = self.client.get("/robots.txt")
        content = response.content.decode()
        self.assertIn("User-agent: *", content)
        self.assertIn("Disallow: /", content)


class Custom404Test(TestCase):
    def test_returns_404_status(self):
        factory = RequestFactory()
        request = factory.get("/nonexistent")
        response = custom_404(request, exception=None)
        self.assertEqual(response.status_code, 404)


class RootIndexTest(TestCase):
    def test_returns_200(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
