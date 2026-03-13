from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from news.models import NewsArticle


class NewsListAPIViewTest(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        now = timezone.now()
        for i in range(15):
            NewsArticle.objects.create(
                source_guid=f"guid-{i:03d}",
                title=f"Article {i}",
                source_url=f"https://example.com/article-{i}",
                summary=f"Summary for article {i}",
                published_at=now - timezone.timedelta(hours=i),
            )

    def test_list_returns_paginated(self):
        resp = self.client.get("/news/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 15)
        self.assertEqual(len(data["results"]), 12)
        self.assertIsNotNone(data["next"])
        self.assertIsNone(data["previous"])

    def test_page_two(self):
        resp = self.client.get("/news/?page=2")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data["results"]), 3)
        self.assertIsNone(data["next"])

    def test_custom_page_size(self):
        resp = self.client.get("/news/?page_size=5")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["results"]), 5)

    def test_ordering(self):
        resp = self.client.get("/news/")
        results = resp.json()["results"]
        self.assertEqual(results[0]["title"], "Article 0")  # most recent

    def test_no_auth_required(self):
        resp = self.client.get("/news/")
        self.assertEqual(resp.status_code, 200)

    def test_response_fields(self):
        resp = self.client.get("/news/?page_size=1")
        article = resp.json()["results"][0]
        self.assertIn("id", article)
        self.assertIn("title", article)
        self.assertIn("source_url", article)
        self.assertIn("summary", article)
        self.assertIn("image_url", article)
        self.assertIn("published_at", article)
        self.assertNotIn("raw_payload", article)
        self.assertNotIn("source_guid", article)


class NewsDetailAPIViewTest(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.article = NewsArticle.objects.create(
            source_guid="detail-guid-001",
            title="Detail Test Article",
            source_url="https://example.com/detail-article",
            summary="A short summary.",
            content="<p>Full article content with <strong>HTML</strong>.</p>",
            author="Test Author",
            hero_image_url="https://example.com/hero.jpg",
            hero_caption="Photo credit: Test",
            published_at=timezone.now(),
        )

    def test_detail_returns_article(self):
        resp = self.client.get(f"/news/{self.article.id}/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["title"], "Detail Test Article")
        self.assertEqual(data["author"], "Test Author")
        self.assertIn("<strong>HTML</strong>", data["content"])

    def test_detail_includes_content_field(self):
        resp = self.client.get(f"/news/{self.article.id}/")
        data = resp.json()
        self.assertIn("content", data)
        self.assertIn("author", data)

    def test_detail_includes_hero_fields(self):
        resp = self.client.get(f"/news/{self.article.id}/")
        data = resp.json()
        self.assertEqual(data["hero_image_url"], "https://example.com/hero.jpg")
        self.assertEqual(data["hero_caption"], "Photo credit: Test")

    def test_detail_no_auth_required(self):
        resp = self.client.get(f"/news/{self.article.id}/")
        self.assertEqual(resp.status_code, 200)

    def test_detail_not_found(self):
        import uuid

        resp = self.client.get(f"/news/{uuid.uuid4()}/")
        self.assertEqual(resp.status_code, 404)
