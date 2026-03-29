from django.test import TestCase
from rest_framework.test import APIClient

from pages.models import PageView
from pages.services.analytics import flush_sync


class PageViewCreateViewTest(TestCase):
    def setUp(self):
        flush_sync()
        PageView.objects.all().delete()
        self.client = APIClient()

    def test_create_page_view(self):
        response = self.client.post(
            "/analytics/pageview/",
            {"path": "/about", "referrer": "https://google.com"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)

        flush_sync()
        self.assertEqual(PageView.objects.count(), 1)

        pv = PageView.objects.first()
        self.assertEqual(pv.path, "/about")
        self.assertEqual(pv.referrer, "https://google.com")
        self.assertIsNotNone(pv.ip_address)

    def test_create_page_view_minimal(self):
        response = self.client.post(
            "/analytics/pageview/",
            {"path": "/"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)

        flush_sync()
        self.assertEqual(PageView.objects.count(), 1)

    def test_create_page_view_missing_path(self):
        response = self.client.post(
            "/analytics/pageview/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

        flush_sync()
        self.assertEqual(PageView.objects.count(), 0)
