from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from pages.models import CMSBlock, CMSPage


class CMSPageAPITest(TestCase):
    # noinspection PyPep8Naming
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def test_get_published_page(self):
        page = CMSPage.objects.create(
            slug="about",
            route="/about",
            title="About",
            page_css_class="about-page",
            status="published",
        )
        CMSBlock.objects.create(
            page=page,
            block_type="rich_text",
            sort_order=0,
            data={"heading": "About Us", "body_html": "<p>Hello</p>"},
        )

        response = self.client.get("/cms/pages/about/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["slug"], "about")
        self.assertEqual(data["route"], "/about")
        self.assertEqual(data["title"], "About")
        self.assertEqual(data["page_css_class"], "about-page")
        self.assertEqual(len(data["blocks"]), 1)
        self.assertEqual(data["blocks"][0]["block_type"], "rich_text")
        self.assertEqual(data["blocks"][0]["data"]["heading"], "About Us")

    def test_draft_page_404_for_public(self):
        CMSPage.objects.create(
            slug="draft-page",
            route="/draft-page",
            title="Draft",
            status="draft",
        )
        response = self.client.get("/cms/pages/draft-page/")
        self.assertEqual(response.status_code, 404)

    def test_nonexistent_page_404(self):
        response = self.client.get("/cms/pages/nonexistent/")
        self.assertEqual(response.status_code, 404)

    def test_blocks_ordered_by_sort_order(self):
        page = CMSPage.objects.create(
            slug="ordered",
            route="/ordered",
            title="Ordered",
            status="published",
        )
        CMSBlock.objects.create(
            page=page,
            block_type="rich_text",
            sort_order=2,
            data={"body_html": "<p>Second</p>"},
        )
        CMSBlock.objects.create(
            page=page,
            block_type="rich_text",
            sort_order=0,
            data={"body_html": "<p>First</p>"},
        )

        response = self.client.get("/cms/pages/ordered/")
        blocks = response.json()["blocks"]
        self.assertEqual(blocks[0]["sort_order"], 0)
        self.assertEqual(blocks[1]["sort_order"], 2)

    def test_soft_deleted_blocks_excluded(self):
        page = CMSPage.objects.create(
            slug="del-block",
            route="/del-block",
            title="Del Block",
            status="published",
        )
        CMSBlock.objects.create(
            page=page,
            block_type="rich_text",
            sort_order=0,
            data={"body_html": "<p>Visible</p>"},
        )
        deleted = CMSBlock.objects.create(
            page=page,
            block_type="rich_text",
            sort_order=1,
            data={"body_html": "<p>Deleted</p>"},
        )
        deleted.delete()  # soft delete

        response = self.client.get("/cms/pages/del-block/")
        self.assertEqual(len(response.json()["blocks"]), 1)

    def test_response_is_cached(self):
        CMSPage.objects.create(
            slug="cached",
            route="/cached",
            title="Cached",
            status="published",
        )

        # First request populates cache
        response1 = self.client.get("/cms/pages/cached/")
        self.assertEqual(response1.status_code, 200)

        # Verify cache hit by checking the cache key exists
        cached = cache.get("cms:page:/cached")
        self.assertIsNotNone(cached)
        self.assertEqual(cached["slug"], "cached")
